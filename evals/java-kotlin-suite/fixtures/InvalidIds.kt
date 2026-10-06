@JvmInline value class CustomerId(val value: Long)
@JvmInline value class OrderId(val value: Long)
fun customerLabel(id: CustomerId) = id.value
val invalid = customerLabel(OrderId(7))
