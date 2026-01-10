"""
ETL Extraction Module
Extracts market item data from raw game data sources (JSON, API, etc.)
"""

from typing import List, Dict, Any, Optional
import os
import json
from datetime import datetime
from pathlib import Path
from models.market_models import (
    MarketItem, ItemType, CostumeSubType, WeaponStats, ArmorStats,
    ItemAttributes, ItemPropertyBonus, ElementalAttribute, PetInfo,
    ItemPrice, ItemRequirement, JobClass
)


class MarketDataExtractor:
    """Extracts market item data from various sources"""

    _EN_ITEM_NAMES_CACHE: Optional[Dict[str, str]] = None
    
    # Element color mapping from JS
    ELEMENT_COLOR_MAP = {
        99: "#22c7e8",   # Lightning
        100: "#dc583b",  # Fire
        101: "#3c6cdf",  # Ice
        102: "#36a321",  # Wind
        103: "#f3cf14",  # Earth
        104: "#b64eec",  # Dark
        251: "#22c7e8",  # Lightning (alternate)
    }
    
    # Stat ID to description mapping
    STAT_MAP = {
        71: "Str",
        72: "Dex",
        73: "Con",
        74: "Int",
        75: "Wis",
        76: "Luc",
        97: "Absorption Rate",
        99: "Lightning",
        100: "Fire",
        101: "Ice",
        102: "Wind",
        103: "Earth",
        104: "Dark",
    }
    
    # Proto stat type mapping
    PROTO_STAT_MAP = {
        "APPLY_RANDOM": "RANDOM",
        "APPLY_NONE": None,
        "APPLY_ACCEDRAIN_RATE": "ACCEDRAIN_RATE",
    }
    
    def __init__(self):
        self.extracted_items: List[MarketItem] = []

    @classmethod
    def _load_en_item_names(cls) -> Dict[str, str]:
        if cls._EN_ITEM_NAMES_CACHE is not None:
            return cls._EN_ITEM_NAMES_CACHE

        base = Path(os.getenv("EXTERNAL_STATIC_OUTPUT_DIR", "./data/external"))
        path = base / "m2_data" / "en" / "item_names.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            cls._EN_ITEM_NAMES_CACHE = {}
            return cls._EN_ITEM_NAMES_CACHE

        # metin2alerts format is typically a dict {"vnum": "Name"}
        if isinstance(raw, dict):
            cls._EN_ITEM_NAMES_CACHE = {str(k): str(v) for k, v in raw.items() if v is not None}
            return cls._EN_ITEM_NAMES_CACHE

        # Fallback: if the JSON is an array, we can't reliably map vnum->name for large vnums.
        cls._EN_ITEM_NAMES_CACHE = {}
        return cls._EN_ITEM_NAMES_CACHE

    @classmethod
    def _english_item_name_for_vnum(cls, vnum: int) -> Optional[str]:
        mapping = cls._load_en_item_names()
        if not mapping:
            return None
        return mapping.get(str(vnum))
    
    def extract_from_json(self, json_data: Dict[str, Any]) -> MarketItem:
        """
        Extract item data from JSON object
        """
        item = self._parse_basic_item_info(json_data)
        self._parse_elemental_attributes(item, json_data)
        self._parse_item_properties(item, json_data)
        self._parse_weapon_stats(item, json_data)
        self._parse_armor_stats(item, json_data)
        self._parse_pet_info(item, json_data)
        self._parse_pricing_info(item, json_data)
        self._parse_special_properties(item, json_data)
        
        return item
    
    def _parse_basic_item_info(self, data: Dict[str, Any]) -> MarketItem:
        """Parse basic item information"""
        vnum = data.get('vnum', 0)
        
        # Handle dragon soul items (vnums 110000-175460)
        if isinstance(vnum, int) and 110000 <= vnum <= 175460 and len(str(vnum)) == 6:
            ds_id = vnum
            vnum = (vnum // 100) * 100
        
        item_type = self._parse_item_type(data.get('type', data.get('Type', 'ITEM_UNKNOWN')))

      
        # The market payload may contain localized names depending on source.
        fallback_name = data.get('name', 'Unknown Item')
        en_name = None
        try:
            en_name = self._english_item_name_for_vnum(int(vnum) if isinstance(vnum, int) else int(str(vnum)))
        except Exception:
            en_name = None

        # Listing context fields (match legacy app.js expectations)
        seller_name = data.get('seller') or data.get('seller_name') or data.get('sellerName')
        job_id_raw = data.get('job', data.get('job_id', data.get('jobId', 0)))
        try:
            job_id = int(job_id_raw or 0)
        except Exception:
            job_id = 0

        category_code = data.get('category') or data.get('category_code') or data.get('categoryCode')
        category_id = None
        if category_code is not None and category_code != "":
            category_id = f"{job_id}-{category_code}"

        quantity_raw = data.get('quantity', data.get('count', data.get('amount', 1)))
        try:
            quantity = int(quantity_raw or 1)
        except Exception:
            quantity = 1

        sockets = data.get('sockets', data.get('Sockets', []))
        if not isinstance(sockets, list):
            sockets = []

        enh_raw = data.get(
            'enhancement_level',
            data.get('enhancementLevel', data.get('plus', data.get('enhancement', 0))),
        )
        try:
            enhancement_level = int(enh_raw or 0)
        except Exception:
            enhancement_level = 0
        
        item = MarketItem(
            vnum=vnum,
            name=en_name or fallback_name,
            item_type=item_type,
            item_subtype=data.get('subtype'),
            icon_filename=data.get('icon_filename', 'default.png'),
            level_requirement=data.get('level_requirement'),
            durability_percentage=data.get('durability_percentage', 100.0),
            enhancement_level=enhancement_level,
            sockets=sockets,
            is_tradeable=data.get('is_tradeable', True),
            is_stackable=data.get('is_stackable', False),
            set_name=data.get('set_name'),

            seller_name=seller_name,
            job_id=job_id,
            category_code=category_code,
            category_id=category_id,
            quantity=quantity,
        )
        
        return item
    
    def _parse_item_type(self, type_str: str) -> ItemType:
        """Convert type string to ItemType enum"""
        try:
            return ItemType(type_str)
        except ValueError:
            return ItemType.UNKNOWN
    
    def _parse_elemental_attributes(self, item: MarketItem, data: Dict[str, Any]):
        """Parse elemental damage/resistance attributes"""
        elem = data.get('elem', [])
        
        if elem and len(elem) >= 2:
            stat_id = elem[0]
            values = elem[1] if isinstance(elem[1], list) else []
            
            if stat_id in self.ELEMENT_COLOR_MAP:
                item.elemental_attributes = ElementalAttribute(
                    stat_id=stat_id,
                    values=values
                )
    
    def _parse_item_properties(self, item: MarketItem, data: Dict[str, Any]):
        """Parse attribute bonuses from raw value properties"""
        attrs = data.get('attrs', [])
        rand = data.get('rand', [])
        
        # Process regular attributes
        if attrs:
            item.attributes = ItemAttributes()
            for attr in attrs:
                if isinstance(attr, (list, tuple)) and len(attr) >= 2:
                    stat_id, value = attr[0], attr[1]
                    # Skip 71/72 if value is 0
                    if stat_id in [71, 72] and value == 0:
                        continue
                    item.attributes.add_attribute(stat_id, value, is_random=False)
        
        # Process random attributes
        if rand:
            if not item.attributes:
                item.attributes = ItemAttributes()
            for rand_attr in rand:
                if isinstance(rand_attr, (list, tuple)) and len(rand_attr) >= 2:
                    stat_id, value = rand_attr[0], rand_attr[1]
                    item.attributes.add_attribute(stat_id, value, is_random=True)
    
    def _parse_weapon_stats(self, item: MarketItem, data: Dict[str, Any]):
        """Parse weapon-specific statistics"""
        if item.item_type != ItemType.WEAPON:
            return
        
        proto = data.get('proto', {})
        
        val0 = int(proto.get('Value0', 0) or 0)
        val1 = int(proto.get('Value1', 0) or 0)
        val2 = int(proto.get('Value2', 0) or 0)
        val3 = int(proto.get('Value3', 0) or 0)
        val4 = int(proto.get('Value4', 0) or 0)
        val5 = int(proto.get('Value5', 0) or 0)
        
        min_atk = val3 + val5
        max_atk = val4 + val5
        min_magic = val1 + val5
        max_magic = val2 + val5
        
        if val3 > 0 and val4 > 0:
            item.weapon_stats = WeaponStats(
                min_physical_attack=min_atk,
                max_physical_attack=max_atk,
                min_magical_attack=min_magic,
                max_magical_attack=max_magic,
                base_attack_bonus=val0
            )
    
    def _parse_armor_stats(self, item: MarketItem, data: Dict[str, Any]):
        """Parse armor-specific statistics"""
        if item.item_type != ItemType.ARMOR:
            return
        
        proto = data.get('proto', {})
        
        val0 = int(proto.get('Value0', 0) or 0)  # Magical defense
        val1 = int(proto.get('Value1', 0) or 0)
        val5 = int(proto.get('Value5', 0) or 0)
        
        def_value = val1 + (val5 * 2)
        
        if def_value > 0:
            item.armor_stats = ArmorStats(
                defense_value=def_value,
                magical_defense_value=val0,
                dodge_rate=0.0
            )
    
    def _parse_pet_info(self, item: MarketItem, data: Dict[str, Any]):
        """Parse pet information"""
        if item.item_type != ItemType.PET:
            return
        
        pet_info = data.get('pet_info')
        if not pet_info or not isinstance(pet_info, (list, tuple)) or len(pet_info) < 3:
            return
        
        pet_vnum, pet_type, pet_data = pet_info[0], pet_info[1], pet_info[2]
        
        if not isinstance(pet_data, (list, tuple)) or len(pet_data) < 5:
            return
        
        base_level = pet_data[0]
        evolved_level = pet_data[1]
        created_ts = pet_data[3]
        owner_name = pet_data[4]
        stat_a = pet_data[5] if len(pet_data) > 5 else 0
        stat_b = pet_data[6] if len(pet_data) > 6 else 0
        stat_c = pet_data[7] if len(pet_data) > 7 else 0
        
        item.pet_info = PetInfo(
            pet_vnum=pet_vnum,
            pet_type=pet_type,
            owner_name=owner_name,
            base_level=base_level,
            evolved_level=evolved_level,
            created_timestamp=created_ts,
            stat_hp=stat_a,
            stat_def=stat_b,
            stat_sp=stat_c
        )
    
    def _parse_pricing_info(self, item: MarketItem, data: Dict[str, Any]):
        """Parse pricing information"""
        # metin2alerts payload uses { wonPrice, yangPrice } where yangPrice is the remainder.
        # Total price in yang is computed as: (won * WON_TO_YANG) + yang_remainder.
        yang_remainder = int(data.get('yang_price', data.get('yangPrice', data.get('yang', 0))) or 0)
        won = int(data.get('won_price', data.get('wonPrice', data.get('won', 0))) or 0)

        won_to_yang = int(os.getenv("WON_TO_YANG", "100000000"))
        total_yang = (won * won_to_yang) + yang_remainder

        item.price = ItemPrice(yang_price=total_yang, won_price=won)
    
    def _parse_special_properties(self, item: MarketItem, data: Dict[str, Any]):
        """Parse special properties like changelook, absorption, etc."""
        # Change look / transmog item
        changelook_vnum = data.get('changelookvnum', 0)
        if changelook_vnum > 0:
            item.change_look_vnum = changelook_vnum
        
        # Absorbed item vnum (for auras)
        absorbed_vnum = data.get('absorbed_vnum', 0)
        if absorbed_vnum > 0:
            item.absorption_item_vnum = absorbed_vnum
        
        # Gacha remaining uses
        if item.item_type == ItemType.GACHA:
            sockets = data.get('sockets', [])
            if sockets and len(sockets) > 0 and sockets[0] > 0:
                item.gacha_remaining_uses = sockets[0]
    
    def extract_from_json_array(self, json_array: List[Dict[str, Any]]) -> List[MarketItem]:
        """Extract multiple items from JSON array"""
        items = []
        seen = set()
        for item_data in json_array:
            try:
                item = self.extract_from_json(item_data)
                # Prevent duplicate listings within a single payload.
                # This avoids inflating counts when the same listing appears multiple times.
                key = (
                    int(item.vnum or 0),
                    str(getattr(item.item_type, "value", item.item_type)),
                    int(getattr(item, "enhancement_level", 0) or 0),
                    tuple(int(x or 0) for x in (getattr(item, "sockets", None) or [])),
                    int(getattr(item, "quantity", 1) or 1),
                    str(getattr(item, "category_id", "") or ""),
                    str(getattr(item, "seller_name", "") or "").strip().lower(),
                    int(getattr(getattr(item, "price", None), "yang_price", 0) or 0),
                    int(getattr(getattr(item, "price", None), "won_price", 0) or 0),
                    tuple(
                        sorted(
                            (
                                int(a.stat_id),
                                int(a.value),
                                bool(getattr(a, "is_random", False)),
                            )
                            for a in ((getattr(getattr(item, "attributes", None), "attributes", None) or []) or [])
                        )
                    ),
                    (
                        int(getattr(getattr(item, "elemental_attributes", None), "stat_id", 0) or 0),
                        tuple(int(v or 0) for v in (getattr(getattr(item, "elemental_attributes", None), "values", None) or [])),
                    )
                    if getattr(item, "elemental_attributes", None)
                    else None,
                    int(getattr(item, "change_look_vnum", 0) or 0),
                    int(getattr(item, "absorption_item_vnum", 0) or 0),
                )
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
            except Exception as e:
                print(f"Error extracting item {item_data.get('vnum', 'unknown')}: {e}")
                continue
        
        self.extracted_items = items
        return items
    
    def extract_from_file(self, file_path: str) -> List[MarketItem]:
        """Extract items from JSON file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list):
                return self.extract_from_json_array(data)
            elif isinstance(data, dict) and 'items' in data:
                return self.extract_from_json_array(data['items'])
            else:
                return self.extract_from_json(data) if isinstance(data, dict) else []
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return []


class BatchDataExtractor:
    """Extracts and caches multiple items for batch operations"""
    
    def __init__(self):
        self.extractor = MarketDataExtractor()
        self.cache: Dict[int, MarketItem] = {}
    
    def extract_and_cache(self, json_array: List[Dict[str, Any]]) -> Dict[int, MarketItem]:
        """Extract items and cache by vnum"""
        items = self.extractor.extract_from_json_array(json_array)
        for item in items:
            self.cache[item.vnum] = item
        return self.cache
    
    def get_item(self, vnum: int) -> Optional[MarketItem]:
        """Get cached item by vnum"""
        return self.cache.get(vnum)
    
    def get_items_by_type(self, item_type: ItemType) -> List[MarketItem]:
        """Get all cached items of specific type"""
        return [item for item in self.cache.values() if item.item_type == item_type]
    
    def clear_cache(self):
        """Clear the cache"""
        self.cache.clear()
