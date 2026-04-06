"""
models.py — Core data structures for the TCG simulation engine.

Defines the three primary models:
  - PokemonInstance  : an in-play Pokémon card with runtime state
  - PlayerState      : a single player's zones and resources
  - GameState        : the authoritative snapshot of the full game
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict


# ---------------------------------------------------------------------------
# Card definitions
# ---------------------------------------------------------------------------

@dataclass
class Attack:
    """A single attack available on a Pokémon card."""
    name: str
    cost: List[str]          # e.g. ["Fighting", "Fighting", "Colorless"]
    base_damage: int
    description: str = ""


@dataclass
class CardDefinition:
    """
    Immutable blueprint for any card in the game.
    card_type is one of: "Pokemon", "Energy", "Item", "Stadium", "Tool".
    """
    card_id: str
    name: str
    card_type: str           # "Pokemon" | "Energy" | "Item" | "Stadium" | "Tool"
    # Pokémon-specific fields
    hp: int = 0
    pokemon_type: str = ""   # e.g. "Fighting"
    retreat_cost: int = 0
    attacks: List[Attack] = field(default_factory=list)
    # Energy-specific fields
    energy_type: str = ""    # e.g. "Fighting", "Colorless", "Double"
    provides: List[str] = field(default_factory=list)  # energy symbols provided


# ---------------------------------------------------------------------------
# In-play Pokémon instance
# ---------------------------------------------------------------------------

@dataclass
class PokemonInstance:
    """
    A Pokémon card as it exists in a zone (active or bench).
    Holds mutable runtime state on top of its immutable CardDefinition.
    """
    definition: CardDefinition
    damage_counters: int = 0
    attached_energy: List[CardDefinition] = field(default_factory=list)
    attached_tool: Optional[CardDefinition] = None
    status: Optional[str] = None  # None | "Poisoned" | "Burned" | "Paralyzed" | "Confused" | "Asleep"

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def max_hp(self) -> int:
        return self.definition.hp

    @property
    def current_hp(self) -> int:
        return self.definition.hp - self.damage_counters

    @property
    def is_knocked_out(self) -> bool:
        return self.damage_counters >= self.definition.hp

    def energy_count(self, energy_type: str = "") -> int:
        """Count attached energy of a given type (empty string = any type)."""
        if not energy_type:
            return len(self.attached_energy)
        return sum(
            1 for e in self.attached_energy
            if energy_type in e.provides or e.energy_type == energy_type
        )


# ---------------------------------------------------------------------------
# Player state
# ---------------------------------------------------------------------------

@dataclass
class PlayerState:
    """
    All zones and resources owned by one player.

    Zones:
      deck     – cards remaining in library (ordered list, index 0 = top)
      hand     – cards currently held by the player
      discard  – discard pile
      active   – the single active Pokémon (or None if none is in play)
      bench    – up to 5 benched Pokémon
      prizes   – face-down prize cards
    """
    player_id: str
    deck: List[CardDefinition] = field(default_factory=list)
    hand: List[CardDefinition] = field(default_factory=list)
    discard: List[CardDefinition] = field(default_factory=list)
    active: Optional[PokemonInstance] = None
    bench: List[PokemonInstance] = field(default_factory=list)
    prizes: List[CardDefinition] = field(default_factory=list)
    # Flags
    has_attacked: bool = False
    energy_attached_this_turn: bool = False

    def total_energy_in_discard(self, energy_type: str = "") -> int:
        """Return the count of Energy cards of a given type in the discard."""
        energy_cards = [c for c in self.discard if c.card_type == "Energy"]
        if not energy_type:
            return len(energy_cards)
        return sum(
            1 for e in energy_cards
            if energy_type in e.provides or e.energy_type == energy_type
        )


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    """
    Complete, authoritative snapshot of the game at any point in time.
    The engine mutates this object in-place as actions are applied.
    """
    players: Dict[str, PlayerState] = field(default_factory=dict)
    active_player_id: str = ""
    turn_number: int = 0
    phase: str = "setup"         # "setup" | "draw" | "action" | "attack" | "resolution" | "ended"
    winner: Optional[str] = None
    stadium: Optional[CardDefinition] = None  # active stadium card, if any

    @property
    def active_player(self) -> PlayerState:
        return self.players[self.active_player_id]

    @property
    def opponent(self) -> PlayerState:
        opponent_id = next(pid for pid in self.players if pid != self.active_player_id)
        return self.players[opponent_id]
