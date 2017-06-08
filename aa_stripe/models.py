# -*- coding: utf-8 -*-
import stripe
from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _
from jsonfield import JSONField
from django.core.validators import MinValueValidator, MaxValueValidator
from aa_stripe.exceptions import StripeMethodNotAllowed


class StripeBasicModel(models.Model):
    created = models.DateField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    stripe_response = JSONField()

    class Meta:
        abstract = True


class StripeCustomer(StripeBasicModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stripe_customers')
    stripe_js_response = JSONField()
    stripe_customer_id = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_created_at_stripe = models.BooleanField(default=False)

    def create_at_stripe(self):
        if self.is_created_at_stripe:
            raise StripeMethodNotAllowed()

        stripe.api_key = settings.STRIPE_API_KEY
        customer = stripe.Customer.create(
            source=self.stripe_js_response["id"],
            description="{user.first_name} {user.last_name} id: {user.id}".format(user=self.user)
        )
        self.stripe_customer_id = customer["id"]
        self.stripe_response = customer
        self.is_created_at_stripe = True
        self.save()
        return self

    class Meta:
        ordering = ["id"]


class StripeCharge(StripeBasicModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stripe_charges')
    customer = models.ForeignKey(StripeCustomer, on_delete=models.SET_NULL, null=True)
    amount = models.IntegerField(null=True, help_text=_("in cents"))
    is_charged = models.BooleanField(default=False)
    stripe_charge_id = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=255, help_text=_("Description sent to Stripe"))
    comment = models.CharField(max_length=255, help_text=_("Comment for internal information"))

    def charge(self):
        if self.is_charged:
            raise StripeMethodNotAllowed("Already charded.")

        stripe.api_key = settings.STRIPE_API_KEY
        if self.customer.is_active:
            try:
                stripe_charge = stripe.Charge.create(
                    amount=self.amount,
                    currency="usd",
                    customer=self.customer.stripe_customer_id,
                    description=self.description
                )
            except stripe.error.StripeError:
                self.is_charged = False
                self.save()
                raise

            print (type(stripe_charge))
            self.stripe_charge_id = stripe_charge["id"]
            self.stripe_response = stripe_charge
            self.is_charged = True
            self.save()
            return stripe_charge


class StripeSubscriptionPlan(StripeBasicModel):
    INTERVAL_DAY = "day"
    INTERVAL_WEEK = "week"
    INTERVAL_MONTH = "month"
    INTERVAL_YEAR = "year"

    INTERVAL_CHOICES = (
        (INTERVAL_DAY, INTERVAL_DAY),
        (INTERVAL_WEEK, INTERVAL_WEEK),
        (INTERVAL_MONTH, INTERVAL_MONTH),
        (INTERVAL_YEAR, INTERVAL_YEAR),
    )

    is_created_at_stripe = models.BooleanField(default=False)
    source = JSONField(blank=True, help_text=_("Source of the plan, ie: {\"prescription\": 1}"))
    amount = models.IntegerField(help_text=_("In cents. More: https://stripe.com/docs/api#create_plan-amount"))
    currency = models.CharField(
        max_length=3, help_text=_("3 letter ISO code, default USD, , https://stripe.com/docs/api#create_plan-currency"),
        default="USD")
    name = models.CharField(
        max_length=255, help_text=_("Name of the plan, to be displayed on invoices and in the web interface."))
    interval = models.CharField(
        max_length=10, help_text=_("Specifies billing frequency. Either day, week, month or year."),
        choices=INTERVAL_CHOICES)
    interval_count = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    metadata = JSONField(help_text=_("A set of key/value pairs that you can attach to a plan object. It can be useful"
                         " for storing additional information about the plan in a structured format."))
    statement_descriptor = models.CharField(
        max_length=22, help_text=_("An arbitrary string to be displayed on your customer’s credit card statement."),
        blank=True)
    trial_period_days = models.IntegerField(
        default=0, validators=[MinValueValidator(0)],
        help_text=_("Specifies a trial period in (an integer number of) days. If you include a trial period,"
                    " the customer won’t be billed for the first time until the trial period ends. If the customer "
                    "cancels before the trial period is over, she’ll never be billed at all."))

    def create_at_stripe(self):
        if self.is_created_at_stripe:
            raise StripeMethodNotAllowed()

        stripe.api_key = settings.STRIPE_API_KEY
        try:
            plan = stripe.Plan.create(
                id=self.id,
                amount=self.amount,
                currency=self.currency,
                interval=self.interval,
                interval_count=self.interval_count,
                name=self.name,
                metadata=self.metadata,
                statement_descriptor=self.statement_descriptor,
                trial_period_days=self.trial_period_days
            )
        except stripe.error.StripeError:
            self.is_created_at_stripe = False
            self.save()
            raise

        self.stripe_response = plan
        self.is_created_at_stripe = True
        self.save()
        return plan


class StripeSubscription(StripeBasicModel):
    STATUS_TRIAL = "trialing"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_CANCELED = "canceled"
    STATUS_UNPAID = "unpaid"

    STATUS_CHOICES = (
        (STATUS_TRIAL, STATUS_TRIAL),
        (STATUS_ACTIVE, STATUS_ACTIVE),
        (STATUS_PAST_DUE, STATUS_PAST_DUE),
        (STATUS_CANCELED, STATUS_CANCELED),
        (STATUS_UNPAID, STATUS_UNPAID),
    )
    stripe_subscription_id = models.CharField(max_length=255, blank=True)
    is_created_at_stripe = models.BooleanField(default=False)
    plan = models.ForeignKey(StripeSubscriptionPlan)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stripe_subscriptions")
    customer = models.ForeignKey(StripeCustomer, on_delete=models.SET_NULL, null=True)
    status = models.CharField(
        max_length=255, help_text="https://stripe.com/docs/api/python#subscription_object-status, "
        "empty if not sent created at stripe", blank=True, choices=STATUS_CHOICES)
    metadata = JSONField(help_text="https://stripe.com/docs/api/python#create_subscription-metadata")
    tax_percent = models.DecimalField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], decimal_places=2, max_digits=3,
        help_text="https://stripe.com/docs/api/python#subscription_object-tax_percent")
    application_fee_percent = models.DecimalField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], decimal_places=2, max_digits=3,
        help_text="https://stripe.com/docs/api/python#create_subscription-application_fee_percent")
    coupon = models.CharField(
        max_length=255, blank=True, help_text="https://stripe.com/docs/api/python#create_subscription-coupon")

    def create_at_stripe(self):
        if self.is_created_at_stripe:
            raise StripeMethodNotAllowed()

        stripe.api_key = settings.STRIPE_API_KEY
        if self.customer.is_active:
            try:
                subscription = stripe.Subscription.create(
                    customer=self.customer.stripe_customer_id,
                    plan=self.plan.id,
                    metadata=self.metadata,
                    tax_percent=self.tax_percent,
                    application_fee_percent=self.application_fee_percent,
                    coupon=self.coupon
                )
            except stripe.error.StripeError:
                self.is_created_at_stripe = False
                self.save()
                raise

            self.stripe_subscription_id = subscription["id"]
            self.stripe_response = subscription
            self.is_created_at_stripe = True
            self.status = subscription["status"]
            self.save()
            return subscription
