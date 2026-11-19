from decimal import Decimal

from rest_framework import serializers


class EuroAmountField(serializers.DecimalField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            data = data.replace(',', '.')
        return super().to_internal_value(data)


class RefillAmountInput(serializers.Serializer):
    # Existing API clients use cents. The public form accepts free euro amounts.
    amount = serializers.IntegerField(min_value=50, max_value=50000, required=False)
    amount_eur = EuroAmountField(max_digits=5, decimal_places=2,
                                min_value=Decimal('0.50'), max_value=Decimal('500.00'),
                                required=False)

    def validate(self, attrs):
        if ('amount' in attrs) == ('amount_eur' in attrs):
            raise serializers.ValidationError('Indiquez un seul montant de recharge.')
        if 'amount_eur' in attrs:
            attrs['amount'] = int(attrs.pop('amount_eur') * 100)
        return attrs
