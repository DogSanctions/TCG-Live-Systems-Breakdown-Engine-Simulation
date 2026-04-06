"""
zygarde_simulation.py — Full single-turn simulation featuring Zygarde-GX.

Scenario
--------
Player 1 controls Zygarde-GX as their active Pokémon.
On this turn they will:

  1. [Draw Phase]      Draw a card from the deck.
  2. [Action Phase]    Play "Magma Basin" (Item): search the discard for a
                       Fighting Energy and attach it to Zygarde-GX, placing
                       2 damage counters on it as a cost.
  3. [Action Phase]    Manually attach a second Fighting Energy from hand.
  4. [Action Phase]    Discard 2 Fighting Energy cards from hand as the
                       "Core Enforcer" setup cost (so the discard count
                       boosts the attack's damage).
  5. [Attack Phase]    Declare "Core Enforcer".
                       Base: 50 damage + 10 × (Fighting Energy in discard).
  6. [Resolution Phase] Log final game state.

Card definitions used
---------------------
  Zygarde-GX     — 190 HP, Fighting, attacks: Core Enforcer / Land's Wrath
  Lycanroc-GX    — 180 HP, Fighting, used as the opponent's active Pokémon
  Fighting Energy — basic energy providing [F]
  Magma Basin     — Item card that retrieves a Fighting Energy from discard
"""

from simulation.models import (
    Attack,
    CardDefinition,
    GameState,
    PlayerState,
    PokemonInstance,
)
from simulation.engine import log, begin_turn, advance_phase, end_turn
from simulation.actions import (
    draw_card,
    play_item,
    discard_cards_as_cost,
    attach_energy,
    attach_energy_from_discard,
    declare_attack,
)


# ---------------------------------------------------------------------------
# Card definitions
# ---------------------------------------------------------------------------

def _make_fighting_energy(uid: str) -> CardDefinition:
    return CardDefinition(
        card_id=f"fighting-energy-{uid}",
        name="Fighting Energy",
        card_type="Energy",
        energy_type="Fighting",
        provides=["Fighting"],
    )


ZYGARDE_GX = CardDefinition(
    card_id="zygarde-gx-001",
    name="Zygarde-GX",
    card_type="Pokemon",
    hp=190,
    pokemon_type="Fighting",
    retreat_cost=3,
    attacks=[
        Attack(
            name="Core Enforcer",
            cost=["Fighting", "Fighting", "Colorless"],
            base_damage=50,
            description="+10 damage for each Fighting Energy in your discard pile",
        ),
        Attack(
            name="Land's Wrath",
            cost=["Fighting", "Fighting", "Fighting"],
            base_damage=100,
            description="",
        ),
    ],
)

LYCANROC_GX = CardDefinition(
    card_id="lycanroc-gx-001",
    name="Lycanroc-GX",
    card_type="Pokemon",
    hp=180,
    pokemon_type="Fighting",
    retreat_cost=1,
    attacks=[
        Attack(
            name="Crunch",
            cost=["Colorless", "Colorless"],
            base_damage=50,
            description="",
        ),
    ],
)

MAGMA_BASIN_DAMAGE = 20  # damage counters placed on the Pokémon as Magma Basin's cost

MAGMA_BASIN = CardDefinition(
    card_id="magma-basin-001",
    name="Magma Basin",
    card_type="Item",
)

ITEM_PLACEHOLDER = CardDefinition(
    card_id="professor-research-001",
    name="Professor's Research",
    card_type="Item",
)


# ---------------------------------------------------------------------------
# State builder
# ---------------------------------------------------------------------------

def build_initial_state() -> GameState:
    """
    Construct a minimal but realistic GameState for the simulation.

    Player 1 (p1) — Zygarde-GX player:
      active  : Zygarde-GX (already in play, 20 damage from prior turn)
      hand    : Magma Basin, 3× Fighting Energy, Professor's Research
      deck    : 2× Fighting Energy (for the draw phase)
      discard : 1× Fighting Energy  (seeded so Magma Basin has a target)
      prizes  : 4 generic cards

    Player 2 (p2) — Lycanroc-GX player:
      active  : Lycanroc-GX (full HP, no tools attached)
      deck    : 5 cards (generic)
      prizes  : 4 generic cards
    """
    # --- energy cards for p1 ---
    energy_in_discard = _make_fighting_energy("d1")    # will be recovered by Magma Basin
    energy_hand_1     = _make_fighting_energy("h1")    # manual attachment
    energy_hand_2     = _make_fighting_energy("h2")    # discarded as cost
    energy_hand_3     = _make_fighting_energy("h3")    # discarded as cost
    energy_deck_1     = _make_fighting_energy("k1")    # drawn this turn
    energy_deck_2     = _make_fighting_energy("k2")    # remains in deck

    # Zygarde-GX already has one Fighting Energy attached from a previous turn
    energy_already_attached = _make_fighting_energy("a1")
    zygarde_instance = PokemonInstance(
        definition=ZYGARDE_GX,
        damage_counters=20,                         # took 20 damage last turn
        attached_energy=[energy_already_attached],  # 1 energy pre-attached
    )

    # Generic prize card filler
    def prize_card(n: int) -> CardDefinition:
        return CardDefinition(card_id=f"prize-{n}", name=f"Prize Card {n}", card_type="Item")

    p1 = PlayerState(
        player_id="p1",
        active=zygarde_instance,
        hand=[MAGMA_BASIN, energy_hand_1, energy_hand_2, energy_hand_3, ITEM_PLACEHOLDER],
        deck=[energy_deck_1, energy_deck_2],
        discard=[energy_in_discard],
        prizes=[prize_card(i) for i in range(1, 5)],
    )

    lycanroc_instance = PokemonInstance(
        definition=LYCANROC_GX,
        damage_counters=0,
    )
    p2 = PlayerState(
        player_id="p2",
        active=lycanroc_instance,
        deck=[prize_card(i) for i in range(10, 15)],
        prizes=[prize_card(i) for i in range(5, 9)],
    )

    state = GameState(
        players={"p1": p1, "p2": p2},
        active_player_id="p1",
        turn_number=0,
    )
    return state


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def run_simulation() -> None:
    state = build_initial_state()

    log("SETUP", "=" * 60)
    log("SETUP", "Zygarde-GX Simulation — Single Turn")
    log("SETUP", "=" * 60)
    log("SETUP", f"P1 active  : {state.players['p1'].active.name}  "
                 f"({state.players['p1'].active.current_hp}/{state.players['p1'].active.max_hp} HP)")
    log("SETUP", f"P1 hand    : {[c.name for c in state.players['p1'].hand]}")
    log("SETUP", f"P1 deck    : {len(state.players['p1'].deck)} cards")
    log("SETUP", f"P1 discard : {[c.name for c in state.players['p1'].discard]}")
    log("SETUP", f"P1 energy on Zygarde: {state.players['p1'].active.energy_count()}")
    log("SETUP", f"P2 active  : {state.players['p2'].active.name}  "
                 f"({state.players['p2'].active.current_hp}/{state.players['p2'].active.max_hp} HP)")

    # ------------------------------------------------------------------
    # Turn begins
    # ------------------------------------------------------------------
    begin_turn(state)

    # ==================================================================
    # DRAW PHASE
    # ==================================================================
    log("PHASE", "Entering phase: DRAW")
    draw_card(state, "p1", count=1)

    # ==================================================================
    # ACTION PHASE
    # ==================================================================
    advance_phase(state)   # draw → action

    # Step 1: Play Magma Basin — retrieve Fighting Energy from discard
    # and attach it to Zygarde-GX (with 2 damage counter side-effect)
    p1 = state.players["p1"]
    log("ACTION", "P1 plays 'Magma Basin' to recover a Fighting Energy from discard")
    play_item(state, "p1", MAGMA_BASIN)

    # Magma Basin effect: find a Fighting Energy in discard and attach it
    target_energy = next(
        (c for c in p1.discard if c.card_type == "Energy" and "Fighting" in c.provides),
        None,
    )
    if target_energy is None:
        raise RuntimeError("No Fighting Energy in discard for Magma Basin to retrieve")

    attach_energy_from_discard(state, "p1", target_energy, p1.active)
    # Magma Basin places 2 damage counters on the Pokémon as a cost
    p1.active.damage_counters += MAGMA_BASIN_DAMAGE
    log(
        "EFFECT",
        f"Magma Basin places 2 damage counters on {p1.active.name} "
        f"(now {p1.active.damage_counters}/{p1.active.max_hp} HP remaining: "
        f"{p1.active.current_hp})",
    )

    # Step 2: Manual energy attachment from hand
    energy_to_attach = next(c for c in p1.hand if c.card_type == "Energy")
    log("ACTION", "P1 manually attaches a Fighting Energy from hand")
    attach_energy(state, "p1", energy_to_attach, p1.active)

    # Step 3: Discard 2 Fighting Energy cards from hand as Core Enforcer setup
    # (player deliberately mills energy to boost the attack's damage)
    energies_to_discard = [c for c in p1.hand if c.card_type == "Energy"][:2]
    log("ACTION", "P1 discards 2 Fighting Energy cards to power up Core Enforcer")
    discard_cards_as_cost(state, "p1", energies_to_discard, reason="Core Enforcer setup")

    # Summarise P1's state before attacking
    energy_in_discard_count = p1.total_energy_in_discard("Fighting")
    log(
        "STATE",
        f"Pre-attack — Zygarde-GX energy attached: {p1.active.energy_count()}  |  "
        f"Fighting Energy in discard: {energy_in_discard_count}  |  "
        f"HP remaining: {p1.active.current_hp}/{p1.active.max_hp}",
    )

    # ==================================================================
    # ATTACK PHASE
    # ==================================================================
    advance_phase(state)   # action → attack

    final_damage = declare_attack(state, "p1", "Core Enforcer")

    # ==================================================================
    # RESOLUTION PHASE
    # ==================================================================
    end_turn(state)

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    log("SUMMARY", "=" * 60)
    log("SUMMARY", "End-of-turn game state")
    log("SUMMARY", "=" * 60)
    log("SUMMARY", f"Turn completed    : {state.turn_number}")
    log("SUMMARY", f"Final damage dealt: {final_damage}")

    p2 = state.players["p2"]
    if p2.active:
        log("SUMMARY", f"Lycanroc-GX HP    : {p2.active.current_hp}/{p2.active.max_hp}  "
                       f"(damage counters: {p2.active.damage_counters})")
    else:
        log("SUMMARY", "Lycanroc-GX       : Knocked Out")

    if state.winner:
        log("SUMMARY", f"Winner            : {state.winner}")
    else:
        log("SUMMARY", "Winner            : (game still in progress)")

    log("SUMMARY", f"P1 hand remaining : {[c.name for c in p1.hand]}")
    log("SUMMARY", f"P1 discard pile   : {[c.name for c in p1.discard]}")
    log("SUMMARY", f"P1 prizes left    : {len(p1.prizes)}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_simulation()
