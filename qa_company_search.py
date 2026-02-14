#!/usr/bin/env python3
"""
QA Testing Script for Company Search in Atlantis Plus
Tests various scenarios of company search functionality
"""

import asyncio
from supabase import create_client, Client
import json

SUPABASE_URL = "https://mhdpokigbprnnwmsgzuy.supabase.co"
SUPABASE_KEY = "***REMOVED***"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def print_section(title: str):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print('='*80)

def test_1_yandex_direct_search():
    """Test 1: Direct works_at search for Yandex"""
    print_section("TEST 1: Direct works_at search - Yandex")

    try:
        response = supabase.table('assertion').select(
            'object_value, person:subject_person_id(display_name)'
        ).eq('predicate', 'works_at').or_(
            'object_value.ilike.%yandex%,object_value.ilike.%яндекс%'
        ).limit(50).execute()

        people = {}
        for row in response.data:
            company = row['object_value']
            name = row['person']['display_name']
            if company not in people:
                people[company] = []
            people[company].append(name)

        print(f"\nFound {sum(len(v) for v in people.values())} people across {len(people)} company variants")
        for company, names in sorted(people.items(), key=lambda x: -len(x[1]))[:10]:
            print(f"  {company}: {len(names)} people")

        return {
            'total_people': sum(len(v) for v in people.values()),
            'variants': len(people),
            'top_variant': max(people.items(), key=lambda x: len(x[1]))[0] if people else None
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return {'error': str(e)}

def test_2_tinkoff_renamed():
    """Test 2: Renamed companies - Tinkoff/T-Bank"""
    print_section("TEST 2: Renamed companies - Tinkoff/T-Bank")

    try:
        response = supabase.table('assertion').select(
            'object_value, person:subject_person_id(display_name)'
        ).eq('predicate', 'works_at').or_(
            'object_value.ilike.%tinkoff%,object_value.ilike.%t-bank%,object_value.ilike.%тинькофф%'
        ).execute()

        people = {}
        for row in response.data:
            company = row['object_value']
            name = row['person']['display_name']
            if company not in people:
                people[company] = []
            people[company].append(name)

        print(f"\nFound {sum(len(v) for v in people.values())} people across {len(people)} variants:")
        for company, names in people.items():
            print(f"  {company}: {len(names)} people")

        return {
            'total_people': sum(len(v) for v in people.values()),
            'variants': list(people.keys())
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return {'error': str(e)}

def test_3_bytedance_met_on():
    """Test 3: met_on vs works_at (ByteDance)"""
    print_section("TEST 3: met_on vs works_at - ByteDance")

    try:
        response = supabase.table('assertion').select(
            'predicate, object_value, confidence, person:subject_person_id(display_name)'
        ).or_(
            'object_value.ilike.%bytedance%,object_value.ilike.%byte dance%'
        ).execute()

        by_predicate = {}
        for row in response.data:
            pred = row['predicate']
            if pred not in by_predicate:
                by_predicate[pred] = []
            by_predicate[pred].append({
                'person': row['person']['display_name'],
                'value': row['object_value'],
                'confidence': row['confidence']
            })

        print(f"\nFound {len(response.data)} assertions across {len(by_predicate)} predicates:")
        for pred, items in by_predicate.items():
            print(f"\n  {pred}: {len(items)} assertions")
            for item in items[:3]:
                print(f"    - {item['person']}: {item['value']} (conf: {item['confidence']})")

        return {
            'total_assertions': len(response.data),
            'predicates': list(by_predicate.keys()),
            'has_works_at': 'works_at' in by_predicate,
            'has_met_on': 'met_on' in by_predicate
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return {'error': str(e)}

def test_4_email_domain():
    """Test 4: Email domain search - Carta"""
    print_section("TEST 4: Email domain search - Carta")

    try:
        # Find people with @carta.com emails
        email_response = supabase.table('identity').select(
            'value, person:person_id(person_id, display_name)'
        ).eq('namespace', 'email').ilike('value', '%carta.com%').execute()

        print(f"\nFound {len(email_response.data)} people with @carta.com emails")

        if email_response.data:
            person_ids = [row['person']['person_id'] for row in email_response.data]

            # Check their works_at assertions
            works_response = supabase.table('assertion').select(
                'predicate, object_value, person:subject_person_id(display_name)'
            ).in_('subject_person_id', person_ids).in_(
                'predicate', ['works_at', 'role_is']
            ).execute()

            print(f"\nFound {len(works_response.data)} work-related assertions:")
            for row in works_response.data[:10]:
                print(f"  {row['person']['display_name']}: {row['predicate']} = {row['object_value']}")

            return {
                'email_count': len(email_response.data),
                'work_assertions': len(works_response.data),
                'has_carta_works_at': any('carta' in row['object_value'].lower()
                                         for row in works_response.data
                                         if row['predicate'] == 'works_at')
            }

        return {'email_count': 0}
    except Exception as e:
        print(f"ERROR: {e}")
        return {'error': str(e)}

def test_5_embedding_coverage():
    """Test 5: Embedding coverage"""
    print_section("TEST 5: Embedding coverage")

    try:
        # Total count
        total = supabase.table('assertion').select('assertion_id', count='exact').execute()
        with_emb = supabase.table('assertion').select('assertion_id', count='exact').not_.is_('embedding', 'null').execute()

        total_count = total.count
        with_emb_count = with_emb.count
        percentage = (with_emb_count / total_count * 100) if total_count > 0 else 0

        print(f"\nTotal assertions: {total_count}")
        print(f"With embeddings: {with_emb_count}")
        print(f"Coverage: {percentage:.2f}%")

        # By predicate
        predicates_response = supabase.table('assertion').select('predicate').execute()
        predicate_counts = {}
        for row in predicates_response.data:
            pred = row['predicate']
            predicate_counts[pred] = predicate_counts.get(pred, 0) + 1

        print(f"\nTop predicates:")
        for pred, count in sorted(predicate_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {pred}: {count}")

        return {
            'total': total_count,
            'with_embedding': with_emb_count,
            'percentage': percentage,
            'top_predicates': sorted(predicate_counts.items(), key=lambda x: -x[1])[:5]
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return {'error': str(e)}

def test_6_intro_queries():
    """Test 6: Intro queries - Google predicates"""
    print_section("TEST 6: Intro queries - Google predicates")

    try:
        response = supabase.table('assertion').select(
            'predicate'
        ).ilike('object_value', '%google%').execute()

        predicate_counts = {}
        for row in response.data:
            pred = row['predicate']
            predicate_counts[pred] = predicate_counts.get(pred, 0) + 1

        print(f"\nFound {len(response.data)} assertions mentioning Google")
        print("\nPredicates distribution:")
        for pred, count in sorted(predicate_counts.items(), key=lambda x: -x[1]):
            print(f"  {pred}: {count}")

        return {
            'total': len(response.data),
            'predicates': predicate_counts
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return {'error': str(e)}

def test_7_company_variants():
    """Test 7: All company variants analysis"""
    print_section("TEST 7: Company variants analysis")

    try:
        response = supabase.table('assertion').select(
            'object_value, person:subject_person_id(person_id)'
        ).eq('predicate', 'works_at').execute()

        company_people = {}
        for row in response.data:
            company = row['object_value']
            person_id = row['person']['person_id']
            if company not in company_people:
                company_people[company] = set()
            company_people[company].add(person_id)

        # Convert sets to counts
        company_counts = {k: len(v) for k, v in company_people.items()}

        # Filter companies with 5+ people
        big_companies = {k: v for k, v in company_counts.items() if v >= 5}

        print(f"\nTotal unique companies: {len(company_counts)}")
        print(f"Companies with 5+ people: {len(big_companies)}")
        print("\nTop 20 companies:")
        for company, count in sorted(big_companies.items(), key=lambda x: -x[1])[:20]:
            print(f"  {company}: {count} people")

        return {
            'total_companies': len(company_counts),
            'big_companies': len(big_companies),
            'top_20': sorted(big_companies.items(), key=lambda x: -x[1])[:20]
        }
    except Exception as e:
        print(f"ERROR: {e}")
        return {'error': str(e)}

def main():
    print("\n" + "="*80)
    print("  ATLANTIS PLUS - COMPANY SEARCH QA TESTING")
    print("="*80)

    results = {}

    results['test_1'] = test_1_yandex_direct_search()
    results['test_2'] = test_2_tinkoff_renamed()
    results['test_3'] = test_3_bytedance_met_on()
    results['test_4'] = test_4_email_domain()
    results['test_5'] = test_5_embedding_coverage()
    results['test_6'] = test_6_intro_queries()
    results['test_7'] = test_7_company_variants()

    print_section("SUMMARY")
    print(json.dumps(results, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
