"""
engine.py — Turn system and damage calculation pipeline.

Responsibilities:
  - Structured event logging (every action prints a tagged log line)
  - Turn phase advancement: draw → action → attack → resolution
  - Damage calculation pipeline:
      base_damage → modifiers (stadium, tool) → defender reduction → application
"""

from __future__ import annotations
from typing import List, Optional
from simulation.models import GameState, PlayerState, PokemonInstance, CardDefinition


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(event_type: str, message: str) -> None:
    """Print a structured log line to stdout."""
    print(f"[{event_type.upper():>12}]  {message}")


# ---------------------------------------------------------------------------
# Turn phase management
# ---------------------------------------------------------------------------

PHASE_ORDER = ["draw", "action", "attack", "resolution"]


def begin_turn(state: GameState) -> None:
    """Advance to the next turn and reset per-turn flags."""
    state.turn_number += 1
    state.phase = "draw"
    player = state.active_player
    player.has_attacked = False
    player.energy_attached_this_turn = False
    log("TURN", f"=== Turn {state.turn_number} begins — active player: {state.active_player_id} ===")


def advance_phase(state: GameState) -> None:
    """Move the game to the next phase in the turn sequence."""
    current = PHASE_ORDER.index(state.phase) if state.phase in PHASE_ORDER else -1
    if current < len(PHASE_ORDER) - 1:
        state.phase = PHASE_ORDER[current + 1]
        log("PHASE", f"Entering phase: {state.phase.upper()}")
    else:
        state.phase = "resolution"


def end_turn(state: GameState) -> None:
    """Finish the current turn and swap the active player."""
    state.phase = "resolution"
    log("TURN", f"=== Turn {state.turn_number} ends — resolving end-of-turn effects ===")
    _resolve_end_of_turn_statuses(state)
    # Swap active player
    player_ids = list(state.players.keys())
    current_idx = player_ids.index(state.active_player_id)
    state.active_player_id = player_ids[(current_idx + 1) % len(player_ids)]
    log("TURN", f"Active player is now: {state.active_player_id}")


def _resolve_end_of_turn_statuses(state: GameState) -> None:
    """Apply poison/burn damage at the end of the active player's turn."""
    active_pokemon = state.active_player.active
    if active_pokemon is None:
        return
    if active_pokemon.status == "Poisoned":
        active_pokemon.damage_counters += 10
        log("STATUS", f"{active_pokemon.name} is Poisoned — 10 damage added (now {active_pokemon.damage_counters} damage)")
    elif active_pokemon.status == "Burned":
        active_pokemon.damage_counters += 20
        log("STATUS", f"{active_pokemon.name} is Burned — 20 damage added (now {active_pokemon.damage_counters} damage)")


# ---------------------------------------------------------------------------
# Damage calculation pipeline
# ---------------------------------------------------------------------------

def calculate_damage(
    state: GameState,
    attacker: PokemonInstance,
    defender: PokemonInstance,
    base_damage: int,
) -> int:
    """
    Full damage pipeline:
      1. Start with base_damage
      2. Apply attacker modifiers (attached tool)
      3. Apply stadium modifier
      4. Apply defender reduction (damage-reduction tool / resistance)
      5. Clamp to 0
    Returns the final damage value (does NOT apply it).
    """
    log("DAMAGE", f"Pipeline start — base damage: {base_damage}")
    damage = base_damage

    # Step 2: attacker tool modifier
    if attacker.attached_tool is not None:
        bonus = _tool_attack_bonus(attacker.attached_tool)
        if bonus != 0:
            damage += bonus
            log("DAMAGE", f"Tool '{attacker.attached_tool.name}' modifier: {bonus:+d}  → {damage}")

    # Step 3: stadium modifier
    if state.stadium is not None:
        bonus = _stadium_damage_bonus(state.stadium, attacker)
        if bonus != 0:
            damage += bonus
            log("DAMAGE", f"Stadium '{state.stadium.name}' modifier: {bonus:+d}  → {damage}")

    # Step 4: defender reduction
    if defender.attached_tool is not None:
        reduction = _tool_damage_reduction(defender.attached_tool)
        if reduction > 0:
            damage -= reduction
            log("DAMAGE", f"Defender tool '{defender.attached_tool.name}' reduction: -{reduction}  → {damage}")

    # Clamp
    damage = max(0, damage)
    log("DAMAGE", f"Final damage after pipeline: {damage}")
    return damage


def apply_damage(
    state: GameState,
    attacker_player: PlayerState,
    defender_player: PlayerState,
    damage: int,
) -> None:
    """
    Apply computed damage to the defending active Pokémon.
    Handles knock-out detection and prize card taking.
    """
    defender = defender_player.active
    if defender is None:
        log("DAMAGE", "No defending Pokémon — damage not applied")
        return

    defender.damage_counters += damage
    log("DAMAGE", f"{defender.name} now has {defender.damage_counters}/{defender.max_hp} damage counters")

    if defender.is_knocked_out:
        log("KNOCKOUT", f"{defender.name} is Knocked Out!")
        _handle_knockout(state, attacker_player, defender_player)


def _handle_knockout(
    state: GameState,
    attacker_player: PlayerState,
    defender_player: PlayerState,
) -> None:
    """Move the knocked-out Pokémon and attached cards to the discard, take a prize."""
    knocked_out = defender_player.active
    # Move all attached cards to discard
    defender_player.discard.extend(knocked_out.attached_energy)
    if knocked_out.attached_tool:
        defender_player.discard.append(knocked_out.attached_tool)
    defender_player.discard.append(knocked_out.definition)
    defender_player.active = None
    log("KNOCKOUT", f"{knocked_out.name} and its attached cards moved to discard")

    # Attacker takes a prize card (simplified: take 1 prize)
    if attacker_player.prizes:
        prize = attacker_player.prizes.pop(0)
        attacker_player.hand.append(prize)
        log("PRIZE", f"{attacker_player.player_id} takes a prize card: {prize.name} (prizes remaining: {len(attacker_player.prizes)})")
        if not attacker_player.prizes:
            state.winner = attacker_player.player_id
            state.phase = "ended"
            log("GAME", f"{attacker_player.player_id} wins by taking all prize cards!")


# ---------------------------------------------------------------------------
# Helper: tool / stadium effect look-ups (extensible)
# ---------------------------------------------------------------------------

def _tool_attack_bonus(tool: CardDefinition) -> int:
    """Return the damage bonus granted by an attached tool to the attacker."""
    bonuses = {
        "Choice Belt": 30,   # +30 vs. Pokémon V / EX (simplified: always +30 here)
        "Muscle Band": 20,
    }
    return bonuses.get(tool.name, 0)


def _tool_damage_reduction(tool: CardDefinition) -> int:
    """Return the damage reduction granted by an attached tool to the defender."""
    reductions = {
        "Rocky Helmet": 0,   # Rocky Helmet deals damage back, not reduction
        "Protecting Cape": 30,
    }
    return reductions.get(tool.name, 0)


def _stadium_damage_bonus(stadium: CardDefinition, attacker: PokemonInstance) -> int:
    """Return any damage modifier granted by the active stadium."""
    # Example: Fighting Stadium grants +10 to Fighting Pokémon attacks
    if stadium.name == "Fighting Stadium" and attacker.definition.pokemon_type == "Fighting":
        return 10
    return 0
