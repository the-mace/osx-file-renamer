"""Golden names from redacted text dumps. Labeled lines win over the model."""
import os

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures', 'naming')


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as handle:
        return handle.read()


def _filename(info, text):
    from invoice_renamer import (
        apply_document_families,
        _sanitize_document_fields,
        _clean_and_validate_fields,
        _build_filename_parts,
    )

    apply_document_families(info, full_text=text, head_text=text)
    _sanitize_document_fields(info)
    fields = _clean_and_validate_fields(info)
    filename, _ = _build_filename_parts(fields, '.pdf')
    return filename


class TestDocumentFamilyGoldens:
    """Each case is a real miss: the model picked a plausible wrong fact."""

    def test_usaa_policy_line_not_draft_account(self):
        info = {
            'business_name': 'USAA',
            'document_type': 'Statement',
            'document_title': None,
            'invoice_date': '2026-10-05',
            'invoice_number': '008585588',
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': '0529',
        }
        assert _filename(info, _load('usaa_auto_bill.txt')) == 'USAA Auto 7101 20261005.pdf'

    def test_x_money_footer_account_not_routing(self):
        info = {
            'business_name': 'X Money',
            'document_type': 'Statement',
            'document_title': None,
            'invoice_date': '2026-09-30',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Money Market',
            'account_last_4': '011',
        }
        assert _filename(info, _load('x_money_savings_footer.txt')) == (
            'X Money Money Market Statement 8011 20260930.pdf'
        )

    def test_travelers_labeled_coverage_not_brand_guess(self):
        info = {
            'business_name': 'Travelers',
            'document_type': 'Statement',
            'document_title': 'Auto Property',
            'invoice_date': '2026-09-01',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': '4070',
        }
        assert _filename(info, _load('travelers_workers_comp.txt')) == (
            'Travelers Workers Compensation 4070 20260901.pdf'
        )

    def test_amex_closing_date_not_rewards_snapshot(self):
        info = {
            'business_name': 'American Express',
            'document_type': 'Statement',
            'document_title': None,
            'invoice_date': '2026-07-28',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Credit Card',
            'account_last_4': None,
        }
        assert _filename(info, _load('amex_closing_date.txt')) == 'Amex CC Statement 20260828.pdf'

    def test_fidelity_period_end_not_period_start(self):
        info = {
            'business_name': 'Fidelity',
            'document_type': 'Statement',
            'document_title': None,
            'invoice_date': '2026-07-01',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Crypto',
            'account_last_4': None,
        }
        assert _filename(info, _load('fidelity_period.txt')) == 'Fidelity Crypto Statement 20260731.pdf'

    def test_utility_service_location_becomes_topic(self):
        info = {
            'business_name': 'National Grid',
            'document_type': 'Statement',
            'document_title': None,
            'invoice_date': '2026-07-01',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None,
        }
        assert _filename(info, _load('national_grid_barn.txt')) == 'National Grid Barn 5018 20260729.pdf'

    def test_multi_animal_vet_omits_party(self):
        info = {
            'business_name': 'Equine Therapies',
            'document_type': 'Invoice',
            'document_title': None,
            'invoice_date': '2026-08-19',
            'invoice_number': '2384',
            'patient_animal_name': 'Goya',
            'patient_count': None,
            'account_type': None,
            'account_last_4': None,
        }
        filename = _filename(info, _load('equine_multi_patient.txt'))
        assert filename == 'Equine Therapies Invoice 2384 20260819.pdf'
        assert 'Goya' not in filename

    def test_sheraton_property_name_collapses_and_receipt_drops_card(self):
        info = {
            'business_name': 'Sheraton Sand Key Resort',
            'document_type': 'Invoice',
            'document_title': None,
            'invoice_date': '2026-10-01',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Credit Card',
            'account_last_4': '0332',
        }
        assert _filename(info, _load('sheraton_receipt.txt')) == 'Sheraton Receipt 20261001.pdf'

    def test_portal_invoice_id_is_not_a_title(self):
        info = {
            'business_name': 'Starlink',
            'document_type': 'Invoice',
            'document_title': 'Inv Wmurqrb BZK',
            'invoice_date': '2026-09-17',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': '7455',
        }
        filename = _filename(info, _load('starlink_invoice.txt'))
        assert filename == 'Starlink Invoice 7455 20260917.pdf'
        assert 'Wmurqrb' not in filename

    def test_bill_with_payment_receipt_line_stays_invoice(self):
        info = {
            'business_name': 'Berkowitz',
            'document_type': 'Invoice',
            'document_title': None,
            'invoice_date': '2026-10-01',
            'invoice_number': '12345',
            'patient_animal_name': None,
            'account_type': None,
            'account_last_4': None,
        }
        assert _filename(info, _load('berkowitz_bill.txt')) == 'Berkowitz Invoice 3353 20261001.pdf'

    def test_bank_mailing_address_is_not_a_premise(self):
        info = {
            'business_name': 'Bank of America',
            'document_type': 'Statement',
            'document_title': None,
            'invoice_date': '2026-08-01',
            'invoice_number': None,
            'patient_animal_name': None,
            'account_type': 'Checking',
            'account_last_4': None,
        }
        filename = _filename(info, _load('bofa_mailing_address.txt'))
        assert filename == 'BofA Checking Statement 1234 20260831.pdf'
        assert 'Main' not in filename

    def test_no_text_leaves_model_facts_alone(self):
        """Photos and scans have no pdftotext. Families do not invent facts."""
        from invoice_renamer import apply_document_families

        info = {
            'business_name': 'A&L Pool Service',
            'document_type': 'Invoice',
            'document_title': None,
            'invoice_date': '2026-08-05',
            'account_last_4': '4450',
        }
        assert apply_document_families(info, full_text=None, head_text=None) == []
        assert info['business_name'] == 'A&L Pool Service'
        assert info['document_type'] == 'Invoice'


@pytest.mark.parametrize('phrase', [
    'Workers Compensation',
    'NJ Auto 7101',
    'ending in',
])
def test_shared_prompt_does_not_teach_labeled_line_recipes(phrase):
    from invoice_renamer import INVOICE_EXTRACTION_PROMPT

    assert phrase not in INVOICE_EXTRACTION_PROMPT
