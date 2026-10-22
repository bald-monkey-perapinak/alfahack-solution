BEGIN;

-- Профиль может отсутствовать: в платежах есть компании вне основного CSV.
CREATE TABLE organizations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    synthetic_u TEXT UNIQUE,
    name TEXT,                       -- реальные названия в CSV отсутствуют
    industry TEXT,                   -- MAINOKVED_NAME
    okved_code TEXT,
    region TEXT,
    city TEXT,
    group_id TEXT,                   -- идентификатор группы, не контрагент
    annual_revenue NUMERIC(20, 2) CHECK (annual_revenue >= 0),
    has_loans BOOLEAN,
    has_leasing BOOLEAN,
    has_deposits BOOLEAN,
    has_guarantees BOOLEAN,
    has_factoring BOOLEAN,
    has_foreign_trade BOOLEAN,
    foreign_trade_countries TEXT[] NOT NULL DEFAULT '{}',
    -- Остальные исходные колонки сохраняются без потерь, не извлекаются LLM.
    profile_data JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(profile_data) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (synthetic_u IS NOT NULL OR NULLIF(BTRIM(name), '') IS NOT NULL)
);

CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,              -- должность; не роль доступа
    org_id BIGINT NOT NULL REFERENCES organizations(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Исходные наблюдения платежей. Направление денег != направление зависимости.
-- Повторяющиеся пары и платежи самим себе действительно встречаются в CSV.
CREATE TABLE payment_flows (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payer_id BIGINT NOT NULL REFERENCES organizations(id),
    beneficiary_id BIGINT NOT NULL REFERENCES organizations(id),
    amount NUMERIC(24, 2) NOT NULL CHECK (amount >= 0),
    payment_count BIGINT NOT NULL CHECK (payment_count > 0),
    source_ref TEXT NOT NULL,        -- путь/версия исходного датасета
    source_row BIGINT NOT NULL CHECK (source_row > 0),
    UNIQUE (source_ref, source_row)
);

-- Дополнительные зависимости, подтверждённые пользователем или источником.
-- organization_id зависит от counterparty_id; платёж это не доказывает.
CREATE TABLE organization_relations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    counterparty_id BIGINT NOT NULL REFERENCES organizations(id),
    relation_type TEXT NOT NULL CHECK (
        relation_type IN ('supplier', 'buyer', 'partner', 'other')
    ),
    dependency_weight NUMERIC(4, 3) CHECK (dependency_weight BETWEEN 0 AND 1),
    evidence TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (organization_id <> counterparty_id),
    UNIQUE (organization_id, counterparty_id, relation_type)
);

-- Только обезличенные связи из df_Fid_Uid_link_hack.csv.
-- Общее физлицо у компаний не означает цепочку поставок.
CREATE TABLE person_organization_links (
    synthetic_f TEXT NOT NULL,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    city TEXT,
    region TEXT,
    PRIMARY KEY (synthetic_f, organization_id)
);

CREATE TABLE sources (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    website_url TEXT,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('media', 'official', 'bank_analytics', 'other')
    ),
    reliability_score NUMERIC(4, 3) CHECK (reliability_score BETWEEN 0 AND 1)
                                    -- NULL = не оценена
);

-- Общий корпус для внешних новостей и предоставленных Markdown-обзоров банка.
CREATE TABLE materials (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id),
    material_type TEXT NOT NULL CHECK (material_type IN ('news', 'bank_analytics')),
    source_ref TEXT NOT NULL,        -- URL статьи или путь к локальному Markdown
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    summary TEXT,
    published_at TIMESTAMPTZ,        -- NULL, если дата не установлена
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    industries TEXT[] NOT NULL DEFAULT '{}',
    geographies TEXT[] NOT NULL DEFAULT '{}',
    processing_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        processing_status IN ('pending', 'processing', 'ready', 'failed')
    ),
    processing_error TEXT,
    UNIQUE (source_id, source_ref)
);

-- Сохраняем упоминания даже без сопоставления с обезличенным справочником.
CREATE TABLE material_entities (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    material_id BIGINT NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    mention_text TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (
        entity_type IN ('organization', 'person', 'government', 'other')
    ),
    organization_id BIGINT REFERENCES organizations(id),
    match_confidence NUMERIC(4, 3) CHECK (match_confidence BETWEEN 0 AND 1),
    CHECK (organization_id IS NULL OR entity_type = 'organization')
);

-- Один запуск анализа для компании и должности, включая неудачные попытки.
CREATE TABLE analysis_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id),
    target_role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'running', 'completed', 'failed')
    ),
    model_name TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    -- Снимок признаков и использованных связей: профиль позже может измениться.
    company_context JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(company_context) = 'object'),
    -- Массив шагов: инструмент, вход, результат/ссылки, проверка, ошибка.
    steps JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(steps) = 'array'),
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    CHECK ((status IN ('completed', 'failed')) = (finished_at IS NOT NULL))
);

-- Персональная интерпретация отделена от текста статьи и позиции банка.
CREATE TABLE insights (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL UNIQUE REFERENCES analysis_runs(id),
    primary_material_id BIGINT NOT NULL REFERENCES materials(id),
    title TEXT NOT NULL,
    facts TEXT NOT NULL,
    bank_view TEXT,                  -- NULL, если подходящей аналитики не нашли
    interpretation TEXT NOT NULL,
    relevance_reason TEXT NOT NULL,
    risks JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(risks) = 'array'),
    opportunities JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(opportunities) = 'array'),
    suggested_actions JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(suggested_actions) = 'array'),
    relevance_score NUMERIC(4, 3) NOT NULL CHECK (relevance_score BETWEEN 0 AND 1),
    confidence NUMERIC(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Несколько источников на инсайт, с указанием поддерживаемого вывода.
CREATE TABLE insight_evidence (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    insight_id BIGINT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    material_id BIGINT NOT NULL REFERENCES materials(id),
    section TEXT NOT NULL CHECK (
        section IN ('facts', 'bank_view', 'interpretation', 'risks', 'opportunities', 'suggested_actions')
    ),
    claim TEXT NOT NULL,
    quote TEXT NOT NULL,             -- точная выдержка, проверяемая по body
    locator TEXT                    -- раздел/абзац исходного материала
);

CREATE INDEX idx_organizations_group ON organizations(group_id) WHERE group_id IS NOT NULL;
CREATE INDEX idx_organizations_okved ON organizations(okved_code);
CREATE INDEX idx_users_org ON users(org_id);
CREATE INDEX idx_payment_flows_payer ON payment_flows(payer_id, beneficiary_id);
CREATE INDEX idx_payment_flows_beneficiary ON payment_flows(beneficiary_id, payer_id);
CREATE INDEX idx_relations_counterparty ON organization_relations(counterparty_id);
CREATE INDEX idx_person_links_org ON person_organization_links(organization_id);
CREATE INDEX idx_materials_published ON materials(published_at DESC NULLS LAST);
CREATE INDEX idx_materials_status ON materials(processing_status);
CREATE INDEX idx_materials_industries ON materials USING GIN(industries);
CREATE INDEX idx_materials_geographies ON materials USING GIN(geographies);
CREATE INDEX idx_entities_material ON material_entities(material_id);
CREATE INDEX idx_entities_org ON material_entities(organization_id) WHERE organization_id IS NOT NULL;
CREATE INDEX idx_runs_company_role ON analysis_runs(organization_id, target_role, started_at DESC);
CREATE INDEX idx_insights_material ON insights(primary_material_id);
CREATE INDEX idx_evidence_insight ON insight_evidence(insight_id);
CREATE INDEX idx_evidence_material ON insight_evidence(material_id);

COMMIT;
