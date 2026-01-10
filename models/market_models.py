"""
Data Models for Metin2 Market Data Warehouse
Extracted from JavaScript tooltip_helper.js and app.js logic
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ItemType(str, Enum):
    """Item type enumeration based on Metin2 game"""
    WEAPON = "ITEM_WEAPON"
    ARMOR = "ITEM_ARMOR"
    COSTUME = "ITEM_COSTUME"
    RING = "ITEM_RING"
    BELT = "ITEM_BELT"
    GACHA = "ITEM_GACHA"
    QUEST = "ITEM_QUEST"
    PET = "ITEM_PET"
    POLYMORPH = "ITEM_POLYMORPH"
    DS = "ITEM_DS"
    SPECIAL_DS = "ITEM_SPECIAL_DS"
    UNKNOWN = "ITEM_UNKNOWN"


class CostumeSubType(str, Enum):
    """Costume sub-type enumeration"""
    AURA = "COSTUME_AURA"
    ACCE = "COSTUME_ACCE"
    NECK = "ARMOR_NECK"
    EAR = "ARMOR_EAR"
    FOOTS = "ARMOR_FOOTS"
    PENDANT = "ARMOR_PENDANT"
    WRIST = "ARMOR_WRIST"


class JobClass(str, Enum):
    """Metin2 character classes"""
    MUSA = "MUSA"
    ASSASSIN = "ASSASSIN"
    SURA = "SURA"
    MUDANG = "MUDANG"
    WOLFMAN = "WOLFMAN"


@dataclass
class ItemPropertyBonus:
    """Represents a stat/bonus property for an item"""
    stat_id: int
    value: int
    is_random: bool = False
    
    def __post_init__(self):
        """Validate stat value"""
        if not isinstance(self.stat_id, int) or not isinstance(self.value, int):
            raise ValueError("stat_id and value must be integers")


@dataclass
class ElementalAttribute:
    """Represents elemental damage/resistance on items"""
    stat_id: int  # 99-104 or 251-256 for elements
    values: List[int]
    
    ELEMENT_MAP = {
        99: "Lightning", 251: "Lightning",
        100: "Fire", 252: "Fire",
        101: "Ice", 253: "Ice",
        102: "Wind", 254: "Wind",
        103: "Earth", 255: "Earth",
        104: "Dark", 256: "Dark",
    }
    
    @property
    def element_type(self) -> str:
        return self.ELEMENT_MAP.get(self.stat_id, "Unknown")
    
    @property
    def total_value(self) -> int:
        return sum(self.values) if self.values else 0


@dataclass
class WeaponStats:
    """Weapon-specific statistics"""
    min_physical_attack: int
    max_physical_attack: int
    min_magical_attack: int
    max_magical_attack: int
    base_attack_bonus: int = 0
    
    @property
    def average_physical_damage(self) -> float:
        return (self.min_physical_attack + self.max_physical_attack) / 2
    
    @property
    def average_magical_damage(self) -> float:
        if self.min_magical_attack == 0 and self.max_magical_attack == 0:
            return 0
        return (self.min_magical_attack + self.max_magical_attack) / 2
    
    @property
    def damage_consistency(self) -> float:
        """Calculate how consistent the damage is (lower range = more consistent)"""
        phys_range = self.max_physical_attack - self.min_physical_attack
        magic_range = self.max_magical_attack - self.min_magical_attack
        total_range = max(phys_range, magic_range)
        avg_damage = max(self.average_physical_damage, self.average_magical_damage)
        return (avg_damage / (avg_damage + total_range)) * 100 if avg_damage > 0 else 0


@dataclass
class ArmorStats:
    """Armor-specific statistics"""
    defense_value: int
    magical_defense_value: int = 0
    dodge_rate: float = 0.0
    
    @property
    def total_protection(self) -> int:
        return self.defense_value + self.magical_defense_value
    
    @property
    def protection_score(self) -> float:
        """Calculate overall protection effectiveness"""
        base_protection = self.defense_value * 1.0 + self.magical_defense_value * 0.8
        return base_protection + (self.dodge_rate * 10)


@dataclass
class ItemRequirement:
    """Item level/job requirements"""
    requirement_type: str  # LEVEL, JOB, etc.
    minimum_level: Optional[int] = None
    maximum_level: Optional[int] = None
    allowed_jobs: List[JobClass] = field(default_factory=list)
    blocked_jobs: List[JobClass] = field(default_factory=list)


@dataclass
class PetInfo:
    """Pet information and statistics"""
    pet_vnum: int
    pet_type: int
    owner_name: str
    base_level: int
    evolved_level: int
    created_timestamp: int
    stat_hp: float  # HP bonus percentage
    stat_def: float  # Defense bonus percentage
    stat_sp: float  # SP bonus percentage
    lifetime_days: int = 0
    champion_skills: Dict[str, float] = field(default_factory=dict)
    potential_skills: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def is_evolved(self) -> bool:
        return self.evolved_level > 0
    
    @property
    def current_level(self) -> int:
        return self.evolved_level if self.is_evolved else self.base_level


@dataclass
class ItemAttributes:
    """Collection of item attribute bonuses"""
    attributes: List[ItemPropertyBonus] = field(default_factory=list)
    max_attributes: int = 7
    
    def __post_init__(self):
        """Validate attribute count"""
        if len(self.attributes) > self.max_attributes:
            raise ValueError(f"Item cannot have more than {self.max_attributes} attributes")
    
    @property
    def total_attribute_value(self) -> int:
        """Calculate sum of all attribute values"""
        return sum(attr.value for attr in self.attributes)
    
    @property
    def rarity_score(self) -> float:
        """
        Calculate rarity based on attribute count and values
        More attributes and higher values = rarer item
        """
        if not self.attributes:
            return 0.0
        
        count_score = (len(self.attributes) / self.max_attributes) * 50
        value_score = min((self.total_attribute_value / 1000) * 50, 50)
        return count_score + value_score
    
    @property
    def can_add_more_attributes(self) -> bool:
        return len(self.attributes) < self.max_attributes
    
    def add_attribute(self, stat_id: int, value: int, is_random: bool = False):
        """Add a new attribute to the item"""
        # The warehouse schema stores up to 7 attributes. Some raw sources may
        # include more; ignore extras to avoid dropping the entire item.
        if len(self.attributes) >= self.max_attributes:
            return
        self.attributes.append(ItemPropertyBonus(stat_id, value, is_random))


@dataclass
class ItemPrice:
    """Item price information"""
    yang_price: int = 0
    won_price: int = 0
    
    def has_price(self) -> bool:
        return self.yang_price > 0 or self.won_price > 0
    
    def __str__(self) -> str:
        parts = []
        if self.won_price > 0:
            parts.append(f"{self.won_price:,} Won")
        if self.yang_price > 0:
            parts.append(f"{self.yang_price:,} Yang")
        return " / ".join(parts) if parts else "No Price"


@dataclass
class MarketItem:
    """Complete item data model extracted from JS logic"""
    vnum: int
    name: str
    item_type: ItemType
    item_subtype: Optional[str] = None
    icon_filename: str = "default.png"

    # Listing context (from external market payload)
    server_id: Optional[int] = None
    seller_name: Optional[str] = None
    job_id: int = 0
    category_code: Optional[str] = None  # raw code from payload (e.g. "2-0")
    category_id: Optional[str] = None    # derived (e.g. "0-2-0")
    quantity: int = 1
    
    # Item properties
    level_requirement: Optional[int] = None
    durability_percentage: float = 100.0
    
    # Enhancements and sockets
    enhancement_level: int = 0
    sockets: List[int] = field(default_factory=list)
    
    # Attributes and bonuses
    attributes: ItemAttributes = field(default_factory=ItemAttributes)
    elemental_attributes: Optional[ElementalAttribute] = None
    
    # Type-specific stats
    weapon_stats: Optional[WeaponStats] = None
    armor_stats: Optional[ArmorStats] = None
    
    # Special properties
    is_tradeable: bool = True
    is_stackable: bool = False
    change_look_vnum: Optional[int] = None
    absorption_item_vnum: Optional[int] = None
    
    # Pet and gacha
    pet_info: Optional[PetInfo] = None
    gacha_remaining_uses: int = 0
    
    # Pricing
    price: ItemPrice = field(default_factory=ItemPrice)
    
    # Tracking
    set_name: Optional[str] = None
    last_updated: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Validate item data"""
        if not isinstance(self.vnum, int) or self.vnum < 0:
            raise ValueError("Item vnum must be a non-negative integer")
        if not self.name:
            raise ValueError("Item name cannot be empty")
    
    @property
    def is_weapon(self) -> bool:
        return self.item_type == ItemType.WEAPON
    
    @property
    def is_armor(self) -> bool:
        return self.item_type == ItemType.ARMOR
    
    @property
    def is_costume(self) -> bool:
        return self.item_type == ItemType.COSTUME
    
    @property
    def is_aura(self) -> bool:
        return (self.item_type == ItemType.COSTUME and 
                self.item_subtype in [CostumeSubType.AURA.value, CostumeSubType.ACCE.value])
    
    @property
    def is_enhanced(self) -> bool:
        return self.enhancement_level > 0
    
    @property
    def quality_score(self) -> float:
        """
        Calculate overall item quality based on all factors
        Range: 0-100
        """
        score = 0.0
        
        # Weapon quality
        if self.weapon_stats:
            avg_damage = max(self.weapon_stats.average_physical_damage,
                           self.weapon_stats.average_magical_damage)
            score += min((avg_damage / 100) * 30, 30)
        
        # Armor quality
        if self.armor_stats:
            protection = self.armor_stats.total_protection
            score += min((protection / 200) * 30, 30)
        
        # Enhancement bonus
        score += min(self.enhancement_level * 2, 15)
        
        # Attributes bonus
        score += min((self.attributes.rarity_score / 100) * 20, 20)
        
        # Elemental bonus
        if self.elemental_attributes and self.elemental_attributes.total_value > 0:
            score += min((self.elemental_attributes.total_value / 500) * 5, 5)
        
        return min(score, 100.0)
    
    def get_display_name(self) -> str:
        """Get formatted display name with set information"""
        if self.set_name:
            return f"[{self.set_name}] {self.name}"
        return self.name
    
    def estimate_market_value(self) -> int:
        """
        Estimate market value based on item properties
        Returns estimated Yang price
        """
        if self.price.yang_price > 0:
            return self.price.yang_price
        
        base_value = 0
        
        # Base on type and quality
        if self.is_weapon and self.weapon_stats:
            base_value = int(self.weapon_stats.average_physical_damage * 500 + 
                            self.weapon_stats.average_magical_damage * 500)
        elif self.is_armor and self.armor_stats:
            base_value = int(self.armor_stats.total_protection * 100)
        else:
            base_value = 10000
        
        # Multiply by quality factors
        quality_multiplier = 1.0 + (self.quality_score / 100)
        enhancement_multiplier = 1.0 + (self.enhancement_level * 0.15)
        attribute_multiplier = 1.0 + (self.attributes.rarity_score / 100)
        
        estimated_value = int(base_value * quality_multiplier * 
                            enhancement_multiplier * attribute_multiplier)
        
        return estimated_value


@dataclass
class PriceSnapshot:
    """Market price snapshot at a specific time"""
    item_vnum: int
    timestamp: datetime
    price_yang: int
    price_won: int
    quantity_available: int = 1
    enhancement_level: int = 0


@dataclass
class MarketTrend:
    """Price trend analysis result"""
    item_vnum: str
    period: str  # DAILY, WEEKLY, MONTHLY
    average_price: float
    min_price: int
    max_price: int
    price_change_percentage: float
    trend_direction: str  # UP, DOWN, STABLE
    volatility: float
    transaction_count: int


@dataclass
class UndervaluedItem:
    """Identified undervalued item opportunity"""
    item: MarketItem
    current_price: int
    estimated_fair_value: int
    undervaluation_percentage: float
    confidence_score: float  # 0-100
    potential_profit: int
    deal_rating: str  # EXCELLENT, GOOD, FAIR, POOR
    
    @property
    def roi_percentage(self) -> float:
        """Return on Investment percentage"""
        if self.current_price <= 0:
            return 0.0
        return ((self.estimated_fair_value - self.current_price) / self.current_price) * 100
