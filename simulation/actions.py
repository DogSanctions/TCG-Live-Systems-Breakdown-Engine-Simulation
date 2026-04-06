"""
actions.py — All player actions available during the action/attack phases.

Each action:
  - Validates preconditions and raises ValueError on illegal moves
  - Mutates the GameState in-place
  - Emits structured log lines via engine.log()
"""

from __future__ import annotations
from typing import List, Optional
from simulation.models import GameState, PlayerState, PokemonInstance, CardDefinition
from simulation.engine import log, calculate_damage, apply_damage


# ---------------------------------------------------------------------------
# draw_card
# ---------------------------------------------------------------------------

def draw_card(state: GameState, player_id: str, count: int = 1) -> List[CardDefinition]:
    """
    Draw `count` cards from the top of a player's deck into their hand.
    Raises ValueError if the deck is empty (deck-out is a loss in the real game,
    but here we just raise to keep the simulation deterministic).
    """
    player = state.players[player_id]
    drawn: List[CardDefinition] = []
    for _ in range(count):
        if not player.deck:
            raise ValueError(f"{player_id} attempted to draw from an empty deck")
        card = player.deck.pop(0)
        player.hand.append(card)
        drawn.append(card)
        log("DRAW", f"{player_id} draws '{card.name}' (deck size: {len(player.deck)})")
    return drawn


# ---------------------------------------------------------------------------
# play_item
# ---------------------------------------------------------------------------

def play_item(state: GameState, player_id: str, card: CardDefinition) -> None:
    """
    Play an Item card from the player's hand.
    The card is moved from hand to discard and its effect is logged.
    Actual effects (searching, healing, etc.) should be applied by the caller
    after this action records the play event.
    """
    player = state.players[player_id]
    if card not in player.hand:
        raise ValueError(f"{player_id} tried to play '{card.name}' but it is not in hand")
    if card.card_type != "Item":
        raise ValueError(f"'{card.name}' is not an Item card (got: {card.card_type})")
    player.hand.remove(card)
    player.discard.append(card)
    log("ITEM", f"{player_id} plays Item '{card.name}'")


# ---------------------------------------------------------------------------
# discard_cards_as_cost
# ---------------------------------------------------------------------------

def discard_cards_as_cost(
    state: GameState,
    player_id: str,
    cards: List[CardDefinition],
    reason: str = "cost",
) -> None:
    """
    Move `cards` from the player's hand to the discard pile as a paid cost.
    `reason` is a short description logged alongside the action
    (e.g. "Core Enforcer effect", "Magma Basin cost").
    """
    player = state.players[player_id]
    for card in cards:
        if card not in player.hand:
            raise ValueError(
                f"{player_id} tried to discard '{card.name}' as {reason} but it is not in hand"
            )
        player.hand.remove(card)
        player.discard.append(card)
        log("DISCARD", f"{player_id} discards '{card.name}' as {reason}")


# ---------------------------------------------------------------------------
# attach_energy
# ---------------------------------------------------------------------------

def attach_energy(
    state: GameState,
    player_id: str,
    energy_card: CardDefinition,
    target: PokemonInstance,
) -> None:
    """
    Attach one Energy card from the player's hand to a Pokémon.
    Each player may attach one Energy per turn via this manual attachment rule.
    """
    player = state.players[player_id]
    if player.energy_attached_this_turn:
        raise ValueError(f"{player_id} has already attached an Energy this turn")
    if energy_card not in player.hand:
        raise ValueError(
            f"{player_id} tried to attach '{energy_card.name}' but it is not in hand"
        )
    if energy_card.card_type != "Energy":
        raise ValueError(f"'{energy_card.name}' is not an Energy card")

    player.hand.remove(energy_card)
    target.attached_energy.append(energy_card)
    player.energy_attached_this_turn = True
    log(
        "ENERGY",
        f"{player_id} attaches '{energy_card.name}' to {target.name} "
        f"(total energy on {target.name}: {target.energy_count()})",
    )


# ---------------------------------------------------------------------------
# attach_energy_from_discard
# ---------------------------------------------------------------------------

def attach_energy_from_discard(
    state: GameState,
    player_id: str,
    energy_card: CardDefinition,
    target: PokemonInstance,
) -> None:
    """
    Attach an Energy card that is currently in the discard pile to a Pokémon.
    This represents effects like Magma Basin or Zygarde's Core Enforcer recovery.
    Unlike the manual attachment rule, this does NOT consume the once-per-turn
    energy attachment (it is driven by a card effect, not the base game rule).
    """
    player = state.players[player_id]
    if energy_card not in player.discard:
        raise ValueError(
            f"{player_id} tried to attach '{energy_card.name}' from discard "
            f"but it is not in the discard pile"
        )
    if energy_card.card_type != "Energy":
        raise ValueError(f"'{energy_card.name}' is not an Energy card")

    player.discard.remove(energy_card)
    target.attached_energy.append(energy_card)
    log(
        "ENERGY",
        f"{player_id} attaches '{energy_card.name}' from discard to {target.name} "
        f"(total energy on {target.name}: {target.energy_count()})",
    )


# ---------------------------------------------------------------------------
# declare_attack
# ---------------------------------------------------------------------------

def declare_attack(
    state: GameState,
    player_id: str,
    attack_name: str,
) -> int:
    """
    Declare an attack by name.  This function:
      1. Finds the attack on the active Pokémon's definition
      2. Verifies the Pokémon has sufficient attached energy
      3. Runs the full damage pipeline via engine.calculate_damage()
      4. Applies the damage via engine.apply_damage()
      5. Marks the player as having attacked this turn

    Returns the final damage dealt.
    """
    if state.phase not in ("attack", "action"):
        raise ValueError(f"Cannot declare attack during phase '{state.phase}'")

    player = state.players[player_id]
    if player.has_attacked:
        raise ValueError(f"{player_id} has already attacked this turn")

    attacker = player.active
    if attacker is None:
        raise ValueError(f"{player_id} has no active Pokémon to attack with")

    # Find the attack
    attack = next(
        (a for a in attacker.definition.attacks if a.name == attack_name),
        None,
    )
    if attack is None:
        raise ValueError(f"{attacker.name} does not know the attack '{attack_name}'")

    # Check energy requirements
    _verify_energy_cost(attacker, attack.cost)

    opponent = state.opponent
    if opponent.active is None:
        raise ValueError("Opponent has no active Pokémon to attack")

    log(
        "ATTACK",
        f"{player_id}'s {attacker.name} uses '{attack.name}' "
        f"(base damage: {attack.base_damage})"
        + (f" — {attack.description}" if attack.description else ""),
    )

    # Compute bonus damage from special effects (e.g. Core Enforcer)
    base = _compute_effective_base_damage(state, player, attacker, attack)

    # Run damage pipeline
    final_damage = calculate_damage(state, attacker, opponent.active, base)
    apply_damage(state, player, opponent, final_damage)

    player.has_attacked = True
    return final_damage


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _verify_energy_cost(attacker: PokemonInstance, cost: List[str]) -> None:
    """
    Raise ValueError if the attacker does not have enough attached energy
    to pay the attack's cost.  Colorless requirements are met by any energy.
    """
    available = list(attacker.attached_energy)  # shallow copy to consume
    unmet: List[str] = []

    # Try to pay typed costs first
    for energy_type in cost:
        if energy_type == "Colorless":
            continue  # handled in second pass
        matched = next(
            (e for e in available if energy_type in e.provides or e.energy_type == energy_type),
            None,
        )
        if matched:
            available.remove(matched)
        else:
            unmet.append(energy_type)

    # Pay colorless costs with any remaining energy
    colorless_needed = cost.count("Colorless")
    if len(available) < colorless_needed:
        unmet.extend(["Colorless"] * (colorless_needed - len(available)))

    if unmet:
        raise ValueError(
            f"{attacker.name} cannot pay attack cost — missing energy: {unmet}"
        )


def _compute_effective_base_damage(
    state: GameState,
    player: PlayerState,
    attacker: PokemonInstance,
    attack,
) -> int:
    """
    Some attacks have variable base damage based on game state.
    Extend this function to implement per-card effect logic.

    Currently handled:
      - Core Enforcer  : +10 for each Fighting Energy in the discard pile
      - Land's Wrath   : flat base damage, no modifier
    """
    base = attack.base_damage

    if attack.name == "Core Enforcer":
        energy_in_discard = player.total_energy_in_discard("Fighting")
        bonus = energy_in_discard * 10
        log(
            "EFFECT",
            f"Core Enforcer: {energy_in_discard} Fighting Energy in discard → +{bonus} bonus damage",
        )
        base += bonus

    return base
