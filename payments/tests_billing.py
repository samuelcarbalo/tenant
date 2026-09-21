from decimal import Decimal

from django.test import SimpleTestCase

from payments.services.billing import buyer_processing_surcharge, public_processing_breakdown


class PublicProcessingBreakdownTests(SimpleTestCase):
    def test_credits_package_includes_mp_surcharge(self):
        breakdown = public_processing_breakdown(20000)
        self.assertEqual(breakdown["base_amount"], 20000)
        self.assertGreater(breakdown["fee_amount"], 0)
        self.assertEqual(
            breakdown["total_amount"],
            breakdown["base_amount"] + breakdown["fee_amount"],
        )
        self.assertEqual(breakdown["currency"], "COP")
        self.assertEqual(breakdown["fee_amount"], breakdown["payment_fee"])

    def test_matches_buyer_processing_surcharge(self):
        surcharge = buyer_processing_surcharge(45000)
        breakdown = public_processing_breakdown(45000)
        self.assertEqual(breakdown["fee_amount"], int(surcharge["payment_fee"]))
        self.assertEqual(breakdown["total_amount"], int(surcharge["charged_total"]))

    def test_zero_and_negative_base(self):
        zero = public_processing_breakdown(0)
        self.assertEqual(zero["base_amount"], 0)
        self.assertEqual(zero["fee_amount"], 0)
        self.assertEqual(zero["total_amount"], 0)

        negative = public_processing_breakdown(Decimal("-10"))
        self.assertEqual(negative["base_amount"], 0)
        self.assertEqual(negative["total_amount"], 0)
