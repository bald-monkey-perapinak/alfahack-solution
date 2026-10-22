-- Запускать после 001 на отдельной тестовой базе. Все фикстуры откатываются.
BEGIN;

CREATE FUNCTION pg_temp.expect_error(statement TEXT, expected_state TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE actual_state TEXT;
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS actual_state = RETURNED_SQLSTATE;
        IF actual_state = expected_state THEN RETURN; END IF;
        RAISE EXCEPTION 'Expected SQLSTATE %, got %: %', expected_state, actual_state, statement;
    END;
    RAISE EXCEPTION 'Expected SQLSTATE %, statement succeeded: %', expected_state, statement;
END;
$$;

DO $$
DECLARE
    a BIGINT; b BIGINT; c BIGINT;
    media BIGINT; bank BIGINT; article BIGINT; review BIGINT;
    run BIGINT; insight BIGINT; found BOOLEAN;
BEGIN
    INSERT INTO organizations(synthetic_u, industry, has_loans)
        VALUES ('test-A', 'Производство', TRUE) RETURNING id INTO a;
    INSERT INTO organizations(synthetic_u) VALUES ('test-B') RETURNING id INTO b;
    INSERT INTO organizations(synthetic_u) VALUES ('test-C') RETURNING id INTO c;
    INSERT INTO users(name, role, org_id) VALUES ('Тест', 'CFO', a), ('Тест', 'CEO', a);

    -- Повтор пары и self-payment допустимы, повтор исходной строки — нет.
    INSERT INTO payment_flows(payer_id, beneficiary_id, amount, payment_count, source_ref, source_row)
        VALUES (a, b, 100, 2, 'test.csv', 1), (a, b, 50, 1, 'test.csv', 2),
               (b, c, 200, 3, 'test.csv', 3), (a, a, 5, 1, 'test.csv', 4);
    PERFORM pg_temp.expect_error(format(
        'INSERT INTO payment_flows(payer_id,beneficiary_id,amount,payment_count,source_ref,source_row) VALUES(%s,%s,1,1,''test.csv'',1)', a,b), '23505');
    PERFORM pg_temp.expect_error(format(
        'INSERT INTO payment_flows(payer_id,beneficiary_id,amount,payment_count,source_ref,source_row) VALUES(%s,%s,-1,1,''test.csv'',5)', a,b), '23514');

    INSERT INTO organization_relations(organization_id, counterparty_id, relation_type, dependency_weight, evidence)
        VALUES (a,b,'supplier',0.8,'Подтверждено для теста'),
               (b,c,'supplier',0.9,'Подтверждено для теста'),
               (c,a,'partner',0.1,'Цикл для проверки обхода');
    PERFORM pg_temp.expect_error(format(
        'INSERT INTO organization_relations(organization_id,counterparty_id,relation_type,evidence) VALUES(%s,%s,''supplier'',''test'')', a,a), '23514');

    WITH RECURSIVE paths AS (
        SELECT a AS node, ARRAY[a] AS visited, 0 AS depth
        UNION ALL
        SELECT r.counterparty_id, p.visited || r.counterparty_id, p.depth + 1
        FROM paths p JOIN organization_relations r ON r.organization_id = p.node
        WHERE p.depth < 4 AND NOT r.counterparty_id = ANY(p.visited)
    ) SELECT EXISTS(SELECT 1 FROM paths WHERE node=c AND depth=2)
          AND NOT EXISTS(SELECT 1 FROM paths WHERE node=a AND depth>0)
      INTO found;
    IF NOT found THEN RAISE EXCEPTION 'Graph traversal failed'; END IF;

    INSERT INTO person_organization_links(synthetic_f, organization_id)
        VALUES ('test-F',a), ('test-F',b);
    INSERT INTO sources(name, source_type, reliability_score)
        VALUES ('Тест СМИ','media',0.7) RETURNING id INTO media;
    INSERT INTO sources(name, source_type)
        VALUES ('Тест Банк','bank_analytics') RETURNING id INTO bank;
    PERFORM pg_temp.expect_error(
        'INSERT INTO sources(name,source_type,reliability_score) VALUES(''bad'',''media'',1.1)', '23514');

    INSERT INTO materials(source_id, material_type, source_ref, title, body, industries, processing_status)
        VALUES (media,'news','https://example.test/rate','Ставка','Ставка сохранена.',ARRAY['Производство'],'ready')
        RETURNING id INTO article;
    INSERT INTO materials(source_id, material_type, source_ref, title, body, processing_status)
        VALUES (bank,'bank_analytics','ml/data/test.md','Обзор','Стоимость заимствований остаётся высокой.','ready')
        RETURNING id INTO review;
    INSERT INTO material_entities(material_id,mention_text,entity_type)
        VALUES (article,'Неизвестная компания','organization');
    PERFORM pg_temp.expect_error(format(
        'INSERT INTO material_entities(material_id,mention_text,entity_type,organization_id) VALUES(%s,''bad'',''person'',%s)',article,a), '23514');
    PERFORM pg_temp.expect_error(format(
        'INSERT INTO materials(source_id,material_type,source_ref,title,body) VALUES(%s,''news'',''https://example.test/rate'',''duplicate'',''text'')',media), '23505');

    INSERT INTO analysis_runs(organization_id,target_role,status,model_name,pipeline_version,company_context,steps)
        VALUES (a,'CFO','running','test-model','smoke-v1',
                jsonb_build_object('has_loans',true,'path',jsonb_build_array(a,b,c)),
                '[{"tool":"materials.search","result":"test"}]')
        RETURNING id INTO run;
    INSERT INTO insights(run_id,primary_material_id,title,facts,bank_view,interpretation,relevance_reason,
                         risks,suggested_actions,relevance_score,confidence)
        VALUES (run,article,'Стоимость заимствований','Ставка сохранена.',
                'Стоимость заимствований остаётся высокой.','Возможное сохранение расходов по кредитам.',
                'У компании есть кредитный продукт; условия ставки неизвестны.',
                '["Расходы на обслуживание долга"]','["Уточнить условия кредитов"]',0.8,0.6)
        RETURNING id INTO insight;
    INSERT INTO insight_evidence(insight_id,material_id,section,claim,quote)
        VALUES (insight,article,'facts','Ставка сохранена','Ставка сохранена.'),
               (insight,review,'bank_view','Стоимость заимствований высокая','Стоимость заимствований остаётся высокой.');
    UPDATE analysis_runs SET status='completed', finished_at=NOW() WHERE id=run;
    IF (SELECT COUNT(*) FROM insights i JOIN analysis_runs r ON r.id=i.run_id
        WHERE r.organization_id=a AND r.target_role='CFO' AND r.status='completed') <> 1
        THEN RAISE EXCEPTION 'Personalized feed failed'; END IF;
    IF (SELECT COUNT(*) FROM insight_evidence WHERE insight_id=insight) <> 2
        THEN RAISE EXCEPTION 'Evidence failed'; END IF;

    PERFORM pg_temp.expect_error(format(
        'UPDATE insights SET risks=''{}'' WHERE id=%s', insight), '23514');
    PERFORM pg_temp.expect_error(format(
        'UPDATE analysis_runs SET finished_at=NULL WHERE id=%s',run), '23514');
    PERFORM pg_temp.expect_error(format(
        'DELETE FROM materials WHERE id=%s', review), '23503');
    PERFORM pg_temp.expect_error(
        'INSERT INTO organizations(name) VALUES(NULL)', '23514');
    PERFORM pg_temp.expect_error(
        'INSERT INTO users(name,role,org_id) VALUES(''bad'',''CEO'',-1)', '23503');

    INSERT INTO analysis_runs(organization_id,target_role,status,model_name,pipeline_version,error_message,finished_at)
        VALUES (a,'CFO','failed','test-model','smoke-v1','Недоступен инструмент',NOW());
    DELETE FROM insights WHERE id=insight;
    IF EXISTS(SELECT 1 FROM insight_evidence WHERE insight_id=insight)
        THEN RAISE EXCEPTION 'Evidence cascade failed'; END IF;
END;
$$;

ROLLBACK;
\echo 'Schema smoke checks passed; fixtures rolled back.'
