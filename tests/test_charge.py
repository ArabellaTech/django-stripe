"""Test charging users through the StripeCharge model"""
import mock
from aa_stripe.models import StripeCharge, StripeCustomer
from aa_stripe.utils import get_latest_active_customer_for_user
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from stripe.error import StripeError

UserModel = get_user_model()


class TestCharge(TestCase):
    def setUp(self):
        self.user = UserModel.objects.create(email="foo@bar.bar", username="foo", password="dump-password")

    @mock.patch("aa_stripe.management.commands.charge_stripe.stripe.Charge.create")
    def test_charge(self, charge_create_mocked):
        data = {
            "customer_id": "cus_AlSWz1ZQw7qG2z",
            "currency": "usd",
            "amount": 100,
            "description": "ABC"
        }

        charge_create_mocked.return_value = {
            "id": 1
        }
        StripeCustomer.objects.create(
            user=self.user, stripe_customer_id=data["customer_id"], stripe_js_response="foo")
        customer = StripeCustomer.objects.create(
            user=self.user, stripe_customer_id=data["customer_id"], stripe_js_response="foo")
        self.assertTrue(customer, get_latest_active_customer_for_user(self.user))

        charge = StripeCharge.objects.create(user=self.user, amount=data["amount"], customer=customer,
                                             description=data["description"])
        self.assertFalse(charge.is_charged)

        # test in case of an API error
        charge_create_mocked.side_effect = StripeError()
        with self.assertRaises(StripeError):
            call_command("charge_stripe")
            charge.refresh_from_db()
            self.assertFalse(charge.is_charged)

        charge_create_mocked.reset_mock()
        charge_create_mocked.side_effect = None

        # test regular case
        call_command("charge_stripe")
        charge.refresh_from_db()
        self.assertTrue(charge.is_charged)
        charge_create_mocked.assert_called_with(amount=charge.amount, currency=data["currency"],
                                                customer=data["customer_id"], description=data["description"])
