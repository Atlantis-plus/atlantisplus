-- Seed test data for E2E tests
-- Run this against Supabase to create test data for telegram_id 999999999
-- User ID: 03a8479c-dda0-4415-8457-5456a207b5c5

-- Clean up existing test data (if any)
DELETE FROM edge WHERE src_person_id IN (
  SELECT person_id FROM person WHERE owner_id = '03a8479c-dda0-4415-8457-5456a207b5c5'
);
DELETE FROM assertion WHERE subject_person_id IN (
  SELECT person_id FROM person WHERE owner_id = '03a8479c-dda0-4415-8457-5456a207b5c5'
);
DELETE FROM identity WHERE person_id IN (
  SELECT person_id FROM person WHERE owner_id = '03a8479c-dda0-4415-8457-5456a207b5c5'
);
DELETE FROM raw_evidence WHERE owner_id = '03a8479c-dda0-4415-8457-5456a207b5c5';
DELETE FROM person WHERE owner_id = '03a8479c-dda0-4415-8457-5456a207b5c5';

-- Test Person 1: ByteDance employee (for met_on search test)
INSERT INTO person (person_id, owner_id, display_name, status)
VALUES (
  'aaaaaaaa-0001-0000-0000-000000000001'::uuid,
  '03a8479c-dda0-4415-8457-5456a207b5c5'::uuid,
  'Zhang Wei',
  'active'
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0001-0000-0000-000000000001'::uuid,
  'met_on',
  'ByteDance',
  0.9
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0001-0000-0000-000000000001'::uuid,
  'role_is',
  'Senior Engineer',
  0.95
);

-- Test Person 2: Yandex employee (for normalization test)
INSERT INTO person (person_id, owner_id, display_name, status)
VALUES (
  'aaaaaaaa-0002-0000-0000-000000000002'::uuid,
  '03a8479c-dda0-4415-8457-5456a207b5c5'::uuid,
  'Alexey Ivanov',
  'active'
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0002-0000-0000-000000000002'::uuid,
  'works_at',
  'Yandex',
  0.95
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0002-0000-0000-000000000002'::uuid,
  'role_is',
  'Product Manager',
  0.9
);

-- Test Person 3: Яндекс (Cyrillic variant)
INSERT INTO person (person_id, owner_id, display_name, status)
VALUES (
  'aaaaaaaa-0003-0000-0000-000000000003'::uuid,
  '03a8479c-dda0-4415-8457-5456a207b5c5'::uuid,
  'Maria Petrova',
  'active'
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0003-0000-0000-000000000003'::uuid,
  'works_at',
  'Яндекс',
  0.95
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0003-0000-0000-000000000003'::uuid,
  'can_help_with',
  'Machine Learning',
  0.8
);

-- Test Person 4: Startup founder (for threshold test)
INSERT INTO person (person_id, owner_id, display_name, status)
VALUES (
  'aaaaaaaa-0004-0000-0000-000000000004'::uuid,
  '03a8479c-dda0-4415-8457-5456a207b5c5'::uuid,
  'John Smith',
  'active'
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0004-0000-0000-000000000004'::uuid,
  'works_at',
  'TechStartup Inc',
  0.85
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0004-0000-0000-000000000004'::uuid,
  'role_is',
  'Founder & CEO',
  0.9
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0004-0000-0000-000000000004'::uuid,
  'can_help_with',
  'fundraising, startup advice',
  0.8
);

-- Test Person 5: Another ByteDance (different role)
INSERT INTO person (person_id, owner_id, display_name, status)
VALUES (
  'aaaaaaaa-0005-0000-0000-000000000005'::uuid,
  '03a8479c-dda0-4415-8457-5456a207b5c5'::uuid,
  'Li Ming',
  'active'
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0005-0000-0000-000000000005'::uuid,
  'met_on',
  'ByteDance Singapore office',
  0.85
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0005-0000-0000-000000000005'::uuid,
  'works_at',
  'ByteDance',
  0.95
);

INSERT INTO assertion (subject_person_id, predicate, object_value, confidence)
VALUES (
  'aaaaaaaa-0005-0000-0000-000000000005'::uuid,
  'located_in',
  'Singapore',
  0.9
);

-- Raw evidence (optional, for completeness)
INSERT INTO raw_evidence (evidence_id, owner_id, source_type, content, processed)
VALUES (
  'eeeeeeee-0001-0000-0000-000000000001'::uuid,
  '03a8479c-dda0-4415-8457-5456a207b5c5'::uuid,
  'text_note',
  'Met Zhang Wei at ByteDance office visit. Senior engineer on recommendation systems.',
  true
);

INSERT INTO raw_evidence (evidence_id, owner_id, source_type, content, processed)
VALUES (
  'eeeeeeee-0002-0000-0000-000000000002'::uuid,
  '03a8479c-dda0-4415-8457-5456a207b5c5'::uuid,
  'text_note',
  'Alexey from Yandex - product manager, working on search quality.',
  true
);

-- Generate embeddings (placeholder - in real system these would be actual vectors)
-- For now, leave embeddings NULL - they will be generated on first search
