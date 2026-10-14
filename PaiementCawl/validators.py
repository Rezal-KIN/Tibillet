from rest_framework import serializers


class RefillAmountInput(serializers.Serializer):
    amount = serializers.IntegerField(min_value=50, max_value=50000)
