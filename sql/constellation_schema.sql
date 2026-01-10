-- Metin2 Market Data Warehouse - Constellation Schema
-- This schema uses a star schema design with fact and dimension tables

-- ============================================================================
-- DIMENSION TABLES
-- ============================================================================

-- Dimension: Item Information
CREATE TABLE IF NOT EXISTS dim_item (
    item_key SERIAL PRIMARY KEY,
    item_vnum INTEGER UNIQUE NOT NULL,
    item_name VARCHAR(255) NOT NULL,
    item_type VARCHAR(100),
    item_subtype VARCHAR(100),
    icon_filename VARCHAR(255),
    is_tradeable BOOLEAN DEFAULT TRUE,
    is_stackable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dimension: Item Properties (Stats and Bonuses)
CREATE TABLE IF NOT EXISTS dim_item_properties (
    property_key SERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    property_type VARCHAR(100),
    stat_id INTEGER,
    base_value INTEGER,
    max_value INTEGER,
    min_value INTEGER,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(item_key, property_type, stat_id)
);

-- Dimension: Item Requirements
CREATE TABLE IF NOT EXISTS dim_item_requirements (
    requirement_key SERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    requirement_type VARCHAR(100) NOT NULL,  -- e.g., LEVEL, JOB, ETC
    requirement_value INTEGER NOT NULL,
    min_level INTEGER,
    max_level INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(item_key, requirement_type)
);

-- Dimension: Item Categories
CREATE TABLE IF NOT EXISTS dim_item_category (
    category_key SERIAL PRIMARY KEY,
    category_name VARCHAR(100) UNIQUE NOT NULL,
    category_description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dimension: Item Class Restrictions
CREATE TABLE IF NOT EXISTS dim_job_class (
    job_key SERIAL PRIMARY KEY,
    job_name VARCHAR(100) UNIQUE NOT NULL,
    job_code VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dimension: Time (for temporal analysis)
CREATE TABLE IF NOT EXISTS dim_time (
    time_key SERIAL PRIMARY KEY,
    full_date DATE UNIQUE NOT NULL,
    year INTEGER,
    quarter INTEGER,
    month INTEGER,
    week INTEGER,
    day_of_month INTEGER,
    day_of_week INTEGER,
    day_name VARCHAR(20),
    is_weekend BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dimension: Price Category/Range
CREATE TABLE IF NOT EXISTS dim_price_category (
    price_category_key SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL,
    min_price BIGINT,
    max_price BIGINT,
    currency_type VARCHAR(20),  -- YANG, WON
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dimension: Pet Information
CREATE TABLE IF NOT EXISTS dim_pet (
    pet_key SERIAL PRIMARY KEY,
    pet_vnum INTEGER,
    pet_type INTEGER,
    pet_name VARCHAR(255),
    owner_name VARCHAR(255),
    base_level INTEGER,
    evolved_level INTEGER,
    lifetime_days INTEGER,
    stat_hp DECIMAL(5,2),
    stat_def DECIMAL(5,2),
    stat_sp DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dimension: Market Transaction Type
CREATE TABLE IF NOT EXISTS dim_transaction_type (
    transaction_type_key SERIAL PRIMARY KEY,
    transaction_type VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- FACT TABLES
-- ============================================================================

-- Main Fact Table: Market Transactions
CREATE TABLE IF NOT EXISTS fact_market_transaction (
    transaction_key BIGSERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    time_key INTEGER NOT NULL REFERENCES dim_time(time_key),
    transaction_type_key INTEGER NOT NULL REFERENCES dim_transaction_type(transaction_type_key),
    price_category_key INTEGER REFERENCES dim_price_category(price_category_key),

    -- Listing context (external market payload)
    server_id INTEGER,
    seller_name VARCHAR(255),
    job_id INTEGER,
    category_code VARCHAR(50),
    category_id VARCHAR(50),
    
    -- Measures
    transaction_price_yang BIGINT,
    transaction_price_won BIGINT,
    quantity_traded INTEGER DEFAULT 1,
    enhancement_level INTEGER,
    
    -- Attributes from items
    durability_percentage DECIMAL(5,2),
    socket_count INTEGER,
    attribute_count INTEGER,
    
    -- Time tracking
    transaction_timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fact Table: Item Price History
CREATE TABLE IF NOT EXISTS fact_price_history (
    price_history_key BIGSERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    time_key INTEGER NOT NULL REFERENCES dim_time(time_key),
    
    -- Measures
    average_price_yang BIGINT,
    average_price_won BIGINT,
    min_price_yang BIGINT,
    max_price_yang BIGINT,
    min_price_won BIGINT,
    max_price_won BIGINT,
    transaction_count INTEGER,
    total_quantity_traded INTEGER,
    
    -- Metrics
    price_volatility DECIMAL(5,2),
    price_trend VARCHAR(50),  -- UP, DOWN, STABLE
    
    recorded_timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(item_key, time_key)
);

-- Fact Table: Item Attributes Analysis
CREATE TABLE IF NOT EXISTS fact_item_attributes (
    attribute_key BIGSERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    time_key INTEGER NOT NULL REFERENCES dim_time(time_key),

    -- Listing context (external market payload)
    server_id INTEGER,
    seller_name VARCHAR(255),
    job_id INTEGER,
    category_code VARCHAR(50),
    category_id VARCHAR(50),
    
    -- Measures
    attribute_1_stat_id INTEGER,
    attribute_1_value INTEGER,
    attribute_2_stat_id INTEGER,
    attribute_2_value INTEGER,
    attribute_3_stat_id INTEGER,
    attribute_3_value INTEGER,
    attribute_4_stat_id INTEGER,
    attribute_4_value INTEGER,
    attribute_5_stat_id INTEGER,
    attribute_5_value INTEGER,
    attribute_6_stat_id INTEGER,
    attribute_6_value INTEGER,
    attribute_7_stat_id INTEGER,
    attribute_7_value INTEGER,
    
    -- Analysis
    total_attribute_value INTEGER,
    attribute_rarity_score DECIMAL(5,2),
    estimated_value_multiplier DECIMAL(5,2),
    
    recorded_timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fact Table: Undervalued Items Detection
CREATE TABLE IF NOT EXISTS fact_undervalued_items (
    undervalued_key BIGSERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    time_key INTEGER NOT NULL REFERENCES dim_time(time_key),
    
    -- Measures
    current_price_yang BIGINT,
    estimated_fair_value_yang BIGINT,
    undervaluation_percentage DECIMAL(5,2),
    confidence_score DECIMAL(5,2),
    
    -- Opportunity metrics
    potential_profit_yang BIGINT,
    deal_rating VARCHAR(50),  -- EXCELLENT, GOOD, FAIR, POOR
    
    -- Tracking
    detected_timestamp TIMESTAMP NOT NULL,
    is_still_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fact Table: Weapon Analysis
CREATE TABLE IF NOT EXISTS fact_weapon_analysis (
    weapon_key BIGSERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    time_key INTEGER NOT NULL REFERENCES dim_time(time_key),
    
    -- Weapon Stats
    min_physical_attack INTEGER,
    max_physical_attack INTEGER,
    min_magical_attack INTEGER,
    max_magical_attack INTEGER,
    base_attack_bonus INTEGER,
    
    -- Damage Analysis
    average_damage_output DECIMAL(10,2),
    damage_consistency DECIMAL(5,2),
    
    recorded_timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fact Table: Armor Analysis
CREATE TABLE IF NOT EXISTS fact_armor_analysis (
    armor_key BIGSERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    time_key INTEGER NOT NULL REFERENCES dim_time(time_key),
    
    -- Armor Stats
    defense_value INTEGER,
    magical_defense_value INTEGER,
    dodge_rate DECIMAL(5,2),
    
    -- Protection Analysis
    overall_protection_score DECIMAL(10,2),
    magic_resistance DECIMAL(5,2),
    
    recorded_timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fact Table: Pet Equipment Analysis
CREATE TABLE IF NOT EXISTS fact_pet_analysis (
    pet_analysis_key BIGSERIAL PRIMARY KEY,
    pet_key INTEGER NOT NULL REFERENCES dim_pet(pet_key),
    time_key INTEGER NOT NULL REFERENCES dim_time(time_key),
    
    -- Pet Measurements
    level INTEGER,
    experience_points BIGINT,
    skill_count INTEGER,
    potential_skill_count INTEGER,
    
    -- Value Assessment
    pet_value_score DECIMAL(10,2),
    market_demand DECIMAL(5,2),
    
    recorded_timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- AGGREGATE TABLES (for performance optimization)
-- ============================================================================

-- Daily Price Aggregates
CREATE TABLE IF NOT EXISTS agg_daily_price_summary (
    summary_key BIGSERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    date_key INTEGER NOT NULL REFERENCES dim_time(time_key),
    
    avg_price_yang BIGINT,
    avg_price_won BIGINT,
    min_price_yang BIGINT,
    max_price_yang BIGINT,
    transaction_count INTEGER,
    daily_volume INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(item_key, date_key)
);

-- Weekly Price Trends
CREATE TABLE IF NOT EXISTS agg_weekly_price_trends (
    trend_key BIGSERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    year INTEGER,
    week_number INTEGER,
    
    avg_price_yang BIGINT,
    price_change_percentage DECIMAL(5,2),
    transaction_count INTEGER,
    weekly_volume INTEGER,
    trend_direction VARCHAR(50),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(item_key, year, week_number)
);

-- Monthly Performance Summary
CREATE TABLE IF NOT EXISTS agg_monthly_performance (
    performance_key BIGSERIAL PRIMARY KEY,
    item_key INTEGER NOT NULL REFERENCES dim_item(item_key),
    year INTEGER,
    month INTEGER,
    
    avg_price_yang BIGINT,
    min_price_yang BIGINT,
    max_price_yang BIGINT,
    price_volatility DECIMAL(5,2),
    transaction_count INTEGER,
    monthly_volume INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(item_key, year, month)
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- Dimension table indexes
CREATE INDEX idx_dim_item_vnum ON dim_item(item_vnum);
CREATE INDEX idx_dim_item_type ON dim_item(item_type);

-- Fact table indexes (fact_market_transaction)
CREATE INDEX idx_item_time ON fact_market_transaction(item_key, time_key);
CREATE INDEX idx_price ON fact_market_transaction(transaction_price_yang, transaction_price_won);
CREATE INDEX idx_timestamp ON fact_market_transaction(transaction_timestamp);

-- Fact table indexes (fact_price_history)
CREATE INDEX idx_trend_analysis ON fact_price_history(item_key, recorded_timestamp, price_trend);

-- Fact table indexes (fact_item_attributes)
CREATE INDEX idx_rarity ON fact_item_attributes(attribute_rarity_score);
CREATE INDEX idx_item_time_attrs ON fact_item_attributes(item_key, time_key);

-- Fact table indexes (fact_undervalued_items)
CREATE INDEX idx_deal_rating ON fact_undervalued_items(deal_rating, detected_timestamp);
CREATE INDEX idx_confidence ON fact_undervalued_items(confidence_score DESC);

-- Fact table indexes (fact_weapon_analysis)
CREATE INDEX idx_weapon_analysis ON fact_weapon_analysis(item_key, time_key);

-- Fact table indexes (fact_armor_analysis)
CREATE INDEX idx_armor_analysis ON fact_armor_analysis(item_key, time_key);

-- Fact table indexes (fact_pet_analysis)
CREATE INDEX idx_pet_value ON fact_pet_analysis(pet_value_score DESC);

-- ============================================================================
-- VIEWS FOR EASY QUERYING
-- ============================================================================

-- View: Current Market Status
CREATE OR REPLACE VIEW v_current_market_status AS
SELECT 
    di.item_key,
    di.item_vnum,
    di.item_name,
    di.item_type,
    fph.average_price_yang,
    fph.average_price_won,
    fph.min_price_yang,
    fph.max_price_yang,
    fph.price_volatility,
    fph.price_trend,
    fph.transaction_count
FROM dim_item di
LEFT JOIN fact_price_history fph ON di.item_key = fph.item_key
WHERE fph.recorded_timestamp = (
    SELECT MAX(recorded_timestamp) 
    FROM fact_price_history 
    WHERE item_key = di.item_key
);

-- View: Undervalued Opportunities
CREATE OR REPLACE VIEW v_undervalued_opportunities AS
SELECT 
    di.item_vnum,
    di.item_name,
    fui.current_price_yang,
    fui.estimated_fair_value_yang,
    fui.undervaluation_percentage,
    fui.potential_profit_yang,
    fui.confidence_score,
    fui.deal_rating
FROM fact_undervalued_items fui
JOIN dim_item di ON fui.item_key = di.item_key
WHERE fui.is_still_available = TRUE
ORDER BY fui.confidence_score DESC, fui.undervaluation_percentage DESC;

-- View: Price Trends Analysis
CREATE OR REPLACE VIEW v_price_trends_analysis AS
SELECT 
    di.item_vnum,
    di.item_name,
    awpt.year,
    awpt.week_number,
    awpt.avg_price_yang,
    awpt.price_change_percentage,
    awpt.trend_direction,
    awpt.weekly_volume
FROM agg_weekly_price_trends awpt
JOIN dim_item di ON awpt.item_key = di.item_key
ORDER BY di.item_vnum, awpt.year, awpt.week_number;

-- View: High-Value Item Analysis
CREATE OR REPLACE VIEW v_high_value_items AS
SELECT 
    di.item_vnum,
    di.item_name,
    di.item_type,
    fph.average_price_yang,
    fia.total_attribute_value,
    fia.attribute_rarity_score,
    fia.estimated_value_multiplier
FROM dim_item di
LEFT JOIN fact_price_history fph ON di.item_key = fph.item_key
LEFT JOIN fact_item_attributes fia ON di.item_key = fia.item_key
WHERE fph.average_price_yang > 0
ORDER BY fph.average_price_yang DESC;
