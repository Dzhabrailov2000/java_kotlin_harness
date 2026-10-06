import java.util.concurrent.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.flow as coldFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.conflate
import kotlinx.coroutines.flow.toList

typealias CustomerAlias = Long
typealias OrderAlias = Long
data class Snapshot(val items: MutableList<String>)
data class CounterState(val count: Int)

class EndpointBuilder {
    var port = 443
        private set
    fun port(port: Int): EndpointBuilder {
        require(port in 1..65535) { "unexpected port: $port" }
        this.port = port
        return this
    }
}

private var passed = 0
private fun verify(condition: Boolean, name: String) {
    check(condition) { name }
    passed++
    println("PASS $name")
}
private fun acceptsCustomer(id: CustomerAlias) = id

fun main() {
    val order: OrderAlias = 7
    verify(acceptsCustomer(order) == 7L, "typealias does not separate identifiers")
    val previous = Snapshot(mutableListOf("a"))
    val next = previous.copy()
    next.items.add("b")
    verify(previous.items == listOf("a", "b"), "data class copy is shallow")

    val names = listOf("apple", "apricot")
    verify(names.associateBy { it.first() }['a'] == "apricot"
        && names.groupBy { it.first() }['a'] == names,
        "associateBy and groupBy preserve different cardinality")

    var calls = 0
    val lazy = listOf(1, 2).asSequence().map { calls++; it * 2 }
    verify(calls == 0 && lazy.first() == 2 && calls == 1, "Sequence changes evaluation timing")

    val canceled = runCatching { throw CancellationException("stop") }
    verify(canceled.isFailure && canceled.exceptionOrNull() is CancellationException,
        "runCatching captures cancellation instead of propagating it")

    val builder = EndpointBuilder()
    verify(builder.port(1) === builder && builder.port(65535).port == 65535,
        "Valid boundary values preserve builder identity")
    val error = runCatching { builder.port(0) }.exceptionOrNull()
    verify(error is IllegalArgumentException && error.message == "unexpected port: 0" && builder.port == 65535,
        "Rejected argument preserves old state and error contract")

    val state = MutableStateFlow(0)
    var evaluations = 0
    state.update { current ->
        evaluations++
        if (evaluations == 1) state.value = 10
        current + 1
    }
    verify(evaluations == 2 && state.value == 11, "Conflicting CAS repeats update computation")

    val mutable = Snapshot(mutableListOf("a"))
    val flow = MutableStateFlow(mutable)
    mutable.items.add("b")
    val equalCopy = mutable.copy()
    flow.value = equalCopy
    verify(flow.value === mutable && flow.value.items == listOf("a", "b"),
        "Equal StateFlow assignment is not a new immutable snapshot")

    runBlocking {
        var executions = 0
        val cold = coldFlow { executions++; emit(executions) }
        val beforeCollection = executions
        val first = cold.toList()
        val second = cold.toList()
        verify(beforeCollection == 0 && first == listOf(1) && second == listOf(2),
            "Each collection of a cold flow executes its source again")

        var upstreamCatchCalled = false
        var downstreamFailureObserved = false
        try {
            coldFlow { emit(1) }
                .catch { upstreamCatchCalled = true }
                .collect { throw IllegalStateException("downstream") }
        } catch (failure: IllegalStateException) {
            downstreamFailureObserved = failure.message == "downstream"
        }
        verify(!upstreamCatchCalled && downstreamFailureObserved,
            "Flow catch does not consume downstream collector failure")

        val firstReceived = CompletableDeferred<Unit>()
        val releaseCollector = CompletableDeferred<Unit>()
        val seen = mutableListOf<Int>()
        coldFlow {
            emit(1)
            firstReceived.await()
            emit(2)
            emit(3)
            releaseCollector.complete(Unit)
        }.conflate().collect { value ->
            if (value == 1) {
                firstReceived.complete(Unit)
                releaseCollector.await()
            }
            seen.add(value)
        }
        verify(seen == listOf(1, 3), "Conflation drops intermediate values for a slow collector")
    }
    println("KOTLIN_CHECKS=$passed")
}
