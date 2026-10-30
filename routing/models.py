from django.db import models


class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    price = models.DecimalField(max_digits=6, decimal_places=4)  # USD / gallon
    lat = models.FloatField(db_index=True)
    lng = models.FloatField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["lat", "lng"])]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) ${self.price}"
