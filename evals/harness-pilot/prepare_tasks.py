#!/usr/bin/env python3
"""Build new, self-contained executable pilot fixtures. Not skill examples."""
import json
from pathlib import Path
from textwrap import dedent
from observer import LAUNCHER

ROOT = Path(__file__).resolve().parent
TASKS = ROOT / 'tasks'


def put(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(text).lstrip())


BUILD = '''
plugins { kotlin("jvm") version "2.4.10" }
repositories { mavenCentral() }
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web:4.1.0")
    implementation("tools.jackson.module:jackson-module-kotlin:3.1.4")
    implementation("org.jetbrains.kotlin:kotlin-reflect:2.4.10")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
    implementation("org.postgresql:postgresql:42.7.12")
    testImplementation("org.junit.jupiter:junit-jupiter-api:6.1.3")
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:6.1.3")
    testImplementation("org.springframework:spring-test:7.0.8")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:6.1.3")
}
kotlin { jvmToolchain(21) }
tasks.test { useJUnitPlatform(); testLogging { events("failed", "skipped") } }
'''

COMMON = {
 'settings.gradle.kts': 'rootProject.name = "backend-task"\n',
 'build.gradle.kts': BUILD,
 'gradle.properties': 'org.gradle.daemon=false\norg.gradle.workers.max=2\nkotlin.compiler.execution.strategy=in-process\n',
 'gradlew': '#!/bin/sh\nexec gradle --offline --no-daemon --console=plain --max-workers=2 "$@"\n',
 '.gitignore': '.gradle/\nbuild/\n',
 'README.md': '''
 # Backend fixture

 Выполнить задание из запроса в текущем проекте. Исходники в src/main, проверки в src/test.
 Сборка: ./gradlew test. Зависимости уже подготовлены, сеть для загрузки не требуется.
 Исполняемые версии закреплены в build.gradle.kts. Существующие публичные сигнатуры сохраняются,
 если задание явно не разрешает изменение. Файлы сборки и существующие тесты не изменять.
 Можно добавлять свои тесты. Для ревью код не менять, вывод сохранить в review.json.

 Проект самостоятельный: читать другие каталоги, домашнюю директорию и историю других задач
 не требуется. Внешние сервисы, публикация, git push и установка инструментов не нужны.
 '''
}


def fixture(task_id, kind, prompt, sources, tests, oracle=None, rubric=None, mutation=None, sql=False):
    root = TASKS / task_id
    if root.exists():
        raise SystemExit(f'already exists: {root}')
    work = root / 'workspace'
    for name, text in {**COMMON, **sources}.items(): put(work, name, text)
    (work / 'gradlew').chmod(0o755)
    if sql: (work / 'observe-locks').chmod(0o755)
    # Visible smoke checks are intentionally incomplete. The independent verifier adds hidden tests.
    put(work, 'src/test/kotlin/pilot/SmokeTest.kt', '''
        package pilot
        import org.junit.jupiter.api.Test
        import org.junit.jupiter.api.Assertions.assertTrue
        class SmokeTest { @Test fun `runtime starts`() { assertTrue(System.getProperty("java.version").isNotBlank()) } }
    ''')
    for name, text in tests.items(): put(root / 'verifier', name, text)
    for name, text in (oracle or {}).items(): put(root / 'oracle', name, text)
    for name, text in (mutation or {}).items(): put(root / 'mutation', name, text)
    put(root, 'instruction.md', prompt)
    spec = {'id':task_id, 'kind':kind, 'postgres':sql, 'rubric':rubric or {},
            'expected_test_count':{'T01':4,'T02':4,'T03':5,'T04':5,'T05':3,'T06':3}.get(task_id),
            'origin':'New author-created public-domain fixture; no private project code; not copied from skill examples.'}
    (root / 'task.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2)+'\n')


def main():
    fixture('T01', 'implement', '''
        Реализуй HTTP API постановки экспорта в очередь в ExportController. POST /exports принимает JSON
        {"accountId":"...","format":"csv"}. Непустой accountId проверяется после trim, формат только csv
        или json. На неверный ввод ответ 400 и очередь не вызывается. На принятый запрос ответ 202,
        Location: /exports/{id}, JSON {"id":"...","state":"pending"}. Очередь вызывается ровно один раз
        с нормализованным accountId. QueueUnavailableException означает ответ 503, без exception message
        в теле. Экспорт пока не выполнен. Сохрани контракт ExportQueue. Запусти тесты.
    ''', {
      'src/main/kotlin/pilot/ExportQueue.kt': '''
        package pilot
        interface ExportQueue { fun enqueue(accountId: String, format: String): String }
        class QueueUnavailableException(message: String) : RuntimeException(message)
      ''',
      'src/main/kotlin/pilot/ExportController.kt': '''
        package pilot
        import org.springframework.web.bind.annotation.RestController
        @RestController
        class ExportController(private val queue: ExportQueue)
      '''
    }, {'src/test/kotlin/pilot/ExportContractTest.kt': '''
        package pilot
        import org.junit.jupiter.api.Test
        import org.junit.jupiter.api.Assertions.*
        import org.springframework.test.web.servlet.setup.MockMvcBuilders
        import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
        import org.springframework.http.MediaType
        import tools.jackson.databind.json.JsonMapper
        @org.springframework.context.annotation.Configuration(proxyBeanMethods=false)
        @org.springframework.web.servlet.config.annotation.EnableWebMvc
        @org.springframework.context.annotation.ComponentScan(basePackages=["pilot"])
        class FixtureWebConfig
        class ExportContractTest {
          private val mapper = JsonMapper.builder().build()
          private fun request(body: String, queue: ExportQueue): org.springframework.mock.web.MockHttpServletResponse {
            val context = org.springframework.web.context.support.AnnotationConfigWebApplicationContext()
            context.servletContext = org.springframework.mock.web.MockServletContext()
            context.register(FixtureWebConfig::class.java)
            context.addBeanFactoryPostProcessor { factory -> factory.registerSingleton("fixtureExportQueue", queue) }
            context.refresh()
            try {
              return MockMvcBuilders.webAppContextSetup(context).build()
                .perform(post("/exports").contentType(MediaType.APPLICATION_JSON).content(body)).andReturn().response
            } finally { context.close() }
          }
          @Test fun `accepted means queued only and uses normalized account`() {
            val calls=mutableListOf<Pair<String,String>>()
            val q=object:ExportQueue { override fun enqueue(accountId:String,format:String):String { calls.add(accountId to format); return "job-17" } }
            for (format in listOf("csv","json")) {
              calls.clear()
              val r=request("""{"accountId":"  account-2  ","format":"$format"}""",q)
              assertEquals(202,r.status); assertEquals("/exports/job-17",r.getHeader("Location"))
              val body=mapper.readTree(r.contentAsString);assertEquals("job-17",body.get("id").asString());assertEquals("pending",body.get("state").asString())
              assertEquals(listOf("account-2" to format),calls)
            }
          }
          @Test fun `invalid request never queues`() {
            var calls=0
            val q=object:ExportQueue { override fun enqueue(accountId:String,format:String):String { calls++;return "job-1" } }
            for(body in listOf("""{"accountId":" ","format":"csv"}""","""{"accountId":"a","format":"xml"}""","{}","""{"accountId":null,"format":"csv"}""","[")) {
              assertEquals(400,request(body,q).status,body)
            }
            assertEquals(0,calls)
          }
          @Test fun `queue outage does not disclose internal details`() {
            val q=object:ExportQueue { override fun enqueue(accountId:String,format:String):String { throw QueueUnavailableException("internal-secret-marker") } }
            val r=request("""{"accountId":"a","format":"csv"}""",q)
            assertEquals(503,r.status);assertFalse(r.contentAsString.contains("internal-secret-marker"))
          }
        }
    '''}, oracle={'src/main/kotlin/pilot/ExportController.kt': '''
        package pilot
        import org.springframework.http.ResponseEntity
        import org.springframework.web.bind.annotation.*
        import java.net.URI
        @RestController
        class ExportController(private val queue: ExportQueue) {
          @PostMapping("/exports")
          fun submitExport(@RequestBody request: Map<String, String?>): ResponseEntity<*> {
            val account=request["accountId"]?.trim()
            val format=request["format"]
            if(account.isNullOrEmpty() || format !in setOf("csv","json")) return ResponseEntity.badRequest().build<Void>()
            val id=try { queue.enqueue(account, requireNotNull(format)) } catch(e:QueueUnavailableException) { return ResponseEntity.status(503).build<Void>() }
            return ResponseEntity.accepted().location(URI.create("/exports/$id")).body(mapOf("id" to id,"state" to "pending"))
          }
        }
    '''}, rubric={'quality':['Request/response intent is clear; no positional nested container.', 'No speculative layers or public API changes.']})

    fixture('T02','implement','''
        Реализуй SalesReport.summarize. Вход - список продаж, в котором ключ продажи (accountId, orderId).
        Одинаковая пара и полностью одинаковые поля означают повтор доставки и учитываются один раз.
        Если поля для этой пары различаются, брось IllegalArgumentException. Одинаковый orderId у разных
        accountId - разные продажи. Итог сгруппирован по accountId и currency, отсортирован сначала по
        accountId, затем по currency. Суммы BigDecimal складываются без округления, количество означает
        число уникальных заказов. Эквивалентные суммы 2.0 и 2.00 считаются одинаковыми. Пустой вход дает
        пустой результат. Вход не изменять. Сохрани публичные типы, используй понятные промежуточные
        сущности вместо позиционных списков и многослойных нетипизированных Map. Запусти тесты.
    ''', {'src/main/kotlin/pilot/SalesReport.kt': '''
        package pilot
        import java.math.BigDecimal
        data class Sale(val accountId:String,val orderId:String,val currency:String,val amount:BigDecimal)
        data class SalesTotal(val accountId:String,val currency:String,val orders:Int,val amount:BigDecimal)
        class SalesReport { fun summarize(sales:List<Sale>):List<SalesTotal> = TODO("implement") }
    '''}, {'src/test/kotlin/pilot/SalesReportTest.kt': '''
        package pilot
        import java.math.BigDecimal
        import org.junit.jupiter.api.Test
        import org.junit.jupiter.api.Assertions.*
        class SalesReportTest {
          private fun s(a:String,o:String,c:String,n:String)=Sale(a,o,c,BigDecimal(n))
          @Test fun `groups sorts retains accounts and removes only identical deliveries`() {
            val input=mutableListOf(s("b","1","RUB","1.10"),s("a","1","USD","2.0"),s("a","2","USD","3.125"),s("a","1","USD","2.00"),s("a","1b","EUR","4"))
            val before=input.toList();val r=SalesReport().summarize(input)
            assertEquals(listOf("a/EUR","a/USD","b/RUB"),r.map { "${it.accountId}/${it.currency}" })
            assertEquals(listOf(1,2,1),r.map { it.orders })
            assertEquals(0,r[1].amount.compareTo(BigDecimal("5.125")));assertEquals(before,input)
          }
          @Test fun `conflicting duplicates are not silently overwritten`() {
            for(other in listOf(s("a","1","USD","3"),s("a","1","EUR","2"))) {
              assertThrows(IllegalArgumentException::class.java) { SalesReport().summarize(listOf(s("a","1","USD","2"),other)) }
            }
          }
          @Test fun `empty and exact decimal sums`() {
            assertTrue(SalesReport().summarize(emptyList()).isEmpty())
            val r=SalesReport().summarize(listOf(s("a","1","USD","0.1"),s("a","2","USD","0.2")))
            assertEquals(0,r.single().amount.compareTo(BigDecimal("0.3")))
          }
        }
    '''}, oracle={'src/main/kotlin/pilot/SalesReport.kt': '''
        package pilot
        import java.math.BigDecimal
        data class Sale(val accountId:String,val orderId:String,val currency:String,val amount:BigDecimal)
        data class SalesTotal(val accountId:String,val currency:String,val orders:Int,val amount:BigDecimal)
        class SalesReport {
          private data class OrderKey(val accountId:String,val orderId:String)
          private data class TotalKey(val accountId:String,val currency:String)
          fun summarize(sales:List<Sale>):List<SalesTotal> {
            val unique=linkedMapOf<OrderKey,Sale>()
            for(sale in sales) {
              val old=unique.putIfAbsent(OrderKey(sale.accountId,sale.orderId),sale)
              require(old==null || old.currency==sale.currency && old.amount.compareTo(sale.amount)==0)
            }
            return unique.values.groupBy { TotalKey(it.accountId,it.currency) }.map { (key,orders) ->
              SalesTotal(key.accountId,key.currency,orders.size,orders.fold(BigDecimal.ZERO) { n,s -> n+s.amount })
            }.sortedWith(compareBy(SalesTotal::accountId,SalesTotal::currency))
          }
        }
    '''},rubric={'quality':['Named keys rather than List<Any> or positional containers.','No monetary rounding or loss of data hidden behind readability.']})

    batch='''
        package pilot
        import kotlinx.coroutines.*
        import java.io.IOException
        fun interface ItemClient { suspend fun fetch(id:String):String }
        sealed interface ItemResult {
          data class Found(val id:String,val value:String):ItemResult
          data class Failed(val id:String):ItemResult
        }
        class BatchLoader(private val client:ItemClient) {
          suspend fun load(ids:List<String>,parallelism:Int):List<ItemResult> = coroutineScope {
            ids.map { id -> async { runCatching { ItemResult.Found(id,client.fetch(id)) }.getOrElse { ItemResult.Failed(id) } } }.awaitAll()
          }
        }
    '''
    batchtests='''
        package pilot
        import kotlinx.coroutines.*
        import java.io.IOException
        import java.util.concurrent.atomic.AtomicInteger
        import org.junit.jupiter.api.Test
        import org.junit.jupiter.api.Assertions.*
        class BatchLoaderTest {
          @Test fun `limits active requests preserves duplicate inputs and order`() = runBlocking {
            val active=AtomicInteger();val peak=AtomicInteger()
            val client=ItemClient { id -> val n=active.incrementAndGet();peak.accumulateAndGet(n,::maxOf);try { delay(20);id.uppercase() } finally { active.decrementAndGet() } }
            val ids=listOf("b","a","b","c","d","e")
            val result=BatchLoader(client).load(ids,2)
            assertEquals(ids.map { ItemResult.Found(it,it.uppercase()) },result);assertTrue(peak.get()<=2);assertTrue(peak.get()>1)
          }
          @Test fun `io failure is per item and programmer errors propagate`(): Unit = runBlocking {
            val q=BatchLoader(ItemClient { if(it=="bad")throw IOException("down") else it })
            assertEquals(listOf(ItemResult.Failed("bad"),ItemResult.Found("ok","ok")),q.load(listOf("bad","ok"),2))
            assertThrows(IllegalStateException::class.java) { runBlocking { BatchLoader(ItemClient { error("bug") }).load(listOf("x"),1) } }
          }
          @Test fun `client cancellation is never successful data`() {
            assertThrows(CancellationException::class.java) { runBlocking { BatchLoader(ItemClient { throw CancellationException("cancel") }).load(listOf("x"),1) } }
          }
          @Test fun `invalid limit fails before client calls`() {
            var calls=0;val q=BatchLoader(ItemClient { calls++;it })
            for(n in listOf(0,-1))assertThrows(IllegalArgumentException::class.java) { runBlocking { q.load(listOf("x"),n) } }
            assertEquals(0,calls)
          }
        }
    '''
    fixture('T03','repair','''
        Исправь BatchLoader. load сохраняет порядок и повторы ids, одновременно выполняет не больше
        parallelism вызовов клиента и использует параллелизм при нескольких элементах. IOException
        превращается в Failed только для этого элемента. CancellationException и ошибки программы
        должны распространяться вызывающему; отмена не является результатом Failed. parallelism > 0,
        иначе IllegalArgumentException до вызова клиента. Сигнатуры и ItemResult сохраняются.
        Не используй глобальный scope и не блокируй поток. Запусти тесты.
    ''',{'src/main/kotlin/pilot/BatchLoader.kt':batch}, {'src/test/kotlin/pilot/BatchLoaderTest.kt':batchtests},
    oracle={'src/main/kotlin/pilot/BatchLoader.kt':batch[:batch.index('class BatchLoader')]+'''
        class BatchLoader(private val client:ItemClient) {
          suspend fun load(ids:List<String>,parallelism:Int):List<ItemResult> {
            require(parallelism>0)
            val permits=kotlinx.coroutines.sync.Semaphore(parallelism)
            return coroutineScope {
              ids.map { id -> async {
                permits.acquire()
                try { try { ItemResult.Found(id,client.fetch(id)) } catch(e:IOException) { ItemResult.Failed(id) } }
                finally { permits.release() }
              } }.awaitAll()
            }
          }
        }
    '''})

    reader='''
        package pilot;
        import java.io.*;
        import java.util.*;
        import java.util.function.Supplier;
        import java.util.stream.Stream;
        public final class CatalogReader {
          public List<String> read(Supplier<Stream<String>> source, int limit) {
            return source.get().filter(line -> !line.isBlank()).map(String::trim).limit(limit).toList();
          }
        }
    '''
    fixture('T04','repair','''
        Исправь CatalogReader.read. Источник возвращает Stream, владение которым переходит методу.
        Нужно вернуть первые limit непустых после trim строк, порядок и дубликаты сохранить. limit >= 0,
        отрицательное значение дает IllegalArgumentException до открытия источника. При limit == 0
        источник вообще не открывается. Открытый stream всегда закрывается, включая ошибку обхода.
        Не материализуй весь источник: он может быть бесконечным. Первичное исключение обхода должно
        сохраняться, а ошибка закрытия быть suppressed. Не перехватывай ошибки в пустой результат.
        Публичную сигнатуру сохрани. Запусти тесты.
    ''',{'src/main/java/pilot/CatalogReader.java':reader},{'src/test/java/pilot/CatalogReaderTest.java': '''
        package pilot;
        import org.junit.jupiter.api.Test;
        import static org.junit.jupiter.api.Assertions.*;
        import java.util.*;
        import java.util.concurrent.atomic.AtomicInteger;
        import java.util.stream.Stream;
        class CatalogReaderTest {
          @Test void closesSuccessfulReadAndStopsEarly() {
            AtomicInteger closed=new AtomicInteger();AtomicInteger visited=new AtomicInteger();
            var got=new CatalogReader().read(() -> Stream.generate(() -> {visited.incrementAndGet();return " x ";}).onClose(closed::incrementAndGet),3);
            assertEquals(List.of("x","x","x"),got);assertEquals(3,visited.get());assertEquals(1,closed.get());
          }
          @Test void filtersAfterTrim() { assertEquals(List.of("a", Character.toString(0x2003), "b"),new CatalogReader().read(() -> Stream.of("   ", Character.toString(0), " a ", Character.toString(0x2003), "b", "c"),3)); }
          @Test void doesNotOpenForZeroOrInvalidLimit() {
            AtomicInteger opens=new AtomicInteger();
            java.util.function.Supplier<Stream<String>> source=() -> {opens.incrementAndGet();return Stream.of("x");};
            assertEquals(List.of(),new CatalogReader().read(source,0));
            assertThrows(IllegalArgumentException.class,() -> new CatalogReader().read(source,-1));assertEquals(0,opens.get());
          }
          @Test void preservesPrimaryFailureAndSuppressesCloseFailure() {
            var primary=new IllegalStateException("iterate");var closing=new IllegalArgumentException("close");
            var actual=assertThrows(IllegalStateException.class,() -> new CatalogReader().read(() -> Stream.<String>generate(() -> {throw primary;}).onClose(() -> {throw closing;}),1));
            assertSame(primary,actual);assertArrayEquals(new Throwable[]{closing},actual.getSuppressed());
          }
        }
    '''},oracle={'src/main/java/pilot/CatalogReader.java': '''
        package pilot;
        import java.util.*;
        import java.util.function.Supplier;
        import java.util.stream.Stream;
        public final class CatalogReader {
          public List<String> read(Supplier<Stream<String>> source,int limit) {
            if(limit<0)throw new IllegalArgumentException("negative limit");
            if(limit==0)return List.of();
            try(var lines=source.get()) { return lines.map(String::trim).filter(line -> !line.isEmpty()).limit(limit).toList(); }
          }
        }
    '''})

    retrytypes='''
        package pilot
        import java.io.IOException
        data class Charge(val accountId:String,val cents:Long)
        data class Receipt(val id:String)
        class RejectedCharge:RuntimeException()
        fun interface PaymentGateway { fun charge(request:Charge,idempotencyKey:String):Receipt }
    '''
    badretry='''
        package pilot
        import java.io.IOException
        class PaymentService(private val gateway:PaymentGateway,private val newKey:()->String) {
          fun charge(request:Charge):Receipt {
            for(attempt in 1..3) {
              try { return gateway.charge(request,newKey()) }
              catch(e:IOException) { if(attempt==3)throw e }
            }
            error("unreachable")
          }
        }
    '''
    goodretry=badretry.replace('for(attempt in 1..3)', 'val key=newKey()\n            for(attempt in 1..3)').replace('gateway.charge(request,newKey())','gateway.charge(request,key)')
    retrytests='''
        package pilot
        import java.io.IOException
        import org.junit.jupiter.api.Test
        import org.junit.jupiter.api.Assertions.*
        class PaymentContractTest {
          @Test fun `lost response does not repeat charge and key belongs to one logical call`() {
            val paid=mutableMapOf<String,Receipt>();var seq=0;var requests=0
            val gateway=PaymentGateway { _,key -> requests++;val previous=paid[key];if(previous!=null)previous else { paid[key]=Receipt("paid-${paid.size}");throw IOException("response lost after commit") } }
            val service=PaymentService(gateway) { "key-${seq++}" }
            val receipt=service.charge(Charge("a",100));assertEquals("paid-0",receipt.id);assertEquals(1,paid.size);assertEquals(2,requests)
            service.charge(Charge("a",100));assertEquals(2,paid.size)
          }
          @Test fun `rejection is not retried and exhausted io keeps exception`() {
            var calls=0;val rejected=RejectedCharge()
            assertSame(rejected,assertThrows(RejectedCharge::class.java) { PaymentService(PaymentGateway { _,_->calls++;throw rejected }) { "k" }.charge(Charge("a",1)) });assertEquals(1,calls)
            calls=0;val io=IOException("network")
            assertSame(io,assertThrows(IOException::class.java) { PaymentService(PaymentGateway { _,_->calls++;throw io }) { "k" }.charge(Charge("a",1)) });assertEquals(3,calls)
          }
        }
    '''
    review_suffix='''
        Сделай ревью исходников, при необходимости используй терминал и тесты. Код и существующие
        тесты не изменяй. Сохрани review.json вида {"findings":[{"file":"...","line":1,
        "severity":"critical|major","problem":"...","scenario":"...","fix":"..."}]},
        где findings может быть пустым. Включай только доказанные дефекты поведения; стиль и
        предположения о неуказанных требованиях не являются дефектами. Не нужно искать заданное
        число ошибок. В конце кратко сообщи вывод.
    '''
    retry_prompt='''
        Проверь PaymentService. Контракт: один вызов charge - одна логическая оплата. Gateway атомарно
        дедуплицирует по idempotencyKey; IOException может означать потерю ответа ПОСЛЕ списания.
        Повторить IOException можно до трех попыток; RejectedCharge повторять нельзя. Отдельные
        вызовы charge, даже с одинаковыми данными, означают отдельные оплаты. Проверка суммы,
        backoff и долговременное хранение ключей выполняются вызывающим слоем и не входят в задачу.
    '''+review_suffix
    for task_id,source,issue in [('T05',badretry,True),('T06',goodretry,False)]:
      fixture(task_id,'review',retry_prompt,{'src/main/kotlin/pilot/PaymentTypes.kt':retrytypes,'src/main/kotlin/pilot/PaymentService.kt':source},
        {'src/test/kotlin/pilot/PaymentContractTest.kt':retrytests},oracle={'src/main/kotlin/pilot/PaymentService.kt':goodretry} if issue else None,
        mutation=None if issue else {'src/main/kotlin/pilot/PaymentService.kt':badretry},
        rubric={'has_issue':issue,'required_issue':'A fresh idempotency key on each retry can charge again after a committed payment with a lost response.' if issue else None,
                'must_not':['Require deduplication between separate logical calls.', 'Require unspecified backoff or validation.', 'Treat style or a hypothetical change as a present defect.']})

    migration_bad='''
        BEGIN;
        ALTER TABLE accounts ADD CONSTRAINT balance_nonnegative CHECK (balance >= 0) NOT VALID;
        ALTER TABLE accounts VALIDATE CONSTRAINT balance_nonnegative;
        COMMIT;
    '''
    migration_good='''
        BEGIN;
        ALTER TABLE accounts ADD CONSTRAINT balance_nonnegative CHECK (balance >= 0) NOT VALID;
        COMMIT;
        BEGIN;
        ALTER TABLE accounts VALIDATE CONSTRAINT balance_nonnegative;
        COMMIT;
    '''
    migration_prompt='''
        Проверь SQL-миграцию migrations/V2__balance_check.sql для PostgreSQL. accounts - большая
        таблица; balance BIGINT NOT NULL, существующие значения неотрицательны. Цель - добавить и
        провалидировать CHECK balance >= 0. Допустимо кратко заблокировать записи при добавлении
        ограничения, но длительное сканирование VALIDATE не должно удерживать блокировку, которая
        несовместима с обычными SELECT, INSERT и UPDATE. Каждая явная транзакция в SQL исполняется
        отдельно: внешний runner НЕ заворачивает файл целиком в транзакцию. Никакого backfill,
        изменения типа, удаления колонки или дополнительного ограничения не требуется.
        В README описана команда воспроизведения lock modes на подготовленной локальной БД.
    '''+review_suffix
    # Test script observes the lock held after ADD and VALIDATE, before the transaction commits.
    sqlcheck='''
        import json, os, subprocess
        from pathlib import Path
        text=Path('migrations/V2__balance_check.sql').read_text()
        marker="ALTER TABLE accounts VALIDATE CONSTRAINT balance_nonnegative;"
        observation="""SELECT 'LOCK:' || mode FROM pg_locks WHERE pid=pg_backend_pid()
        AND relation='accounts'::regclass ORDER BY mode;"""
        if text.count(marker)!=1: raise SystemExit('fixture verifier expects its declared SQL statement')
        sql="DROP TABLE IF EXISTS accounts;CREATE TABLE accounts(id BIGINT PRIMARY KEY,balance BIGINT NOT NULL);INSERT INTO accounts VALUES(1,10);\\n"+text.replace(marker,marker+'\\n'+observation)
        p=subprocess.run(['docker','exec','-i',os.environ['PILOT_PG_CONTAINER'],'psql','-U','postgres','-v','ON_ERROR_STOP=1','-At'],input=sql,text=True,capture_output=True)
        print(p.stdout);print(p.stderr)
        modes=[line[5:] for line in p.stdout.splitlines() if line.startswith('LOCK:')]
        result={'applied':p.returncode==0,'lock_modes_during_validation':modes,'blocks_regular_writes':'AccessExclusiveLock' in modes or 'ShareLock' in modes or 'ShareRowExclusiveLock' in modes}
        Path('lock-observation.json').write_text(json.dumps(result,indent=2))
        assert result['applied'],p.stderr
        assert modes,'No lock observation'
        assert not result['blocks_regular_writes'],modes
    '''
    for task_id,sql,issue in [('T07',migration_bad,True),('T08',migration_good,False)]:
      fixture(task_id,'review',migration_prompt,{'migrations/V2__balance_check.sql':sql,'observe-locks':LAUNCHER,
        'README.md':COMMON['README.md']+'''
        ## Проверка PostgreSQL
        ./observe-locks запускает исходный SQL с диагностикой pg_locks в локальном PostgreSQL.
        Команда не оценивает правильность и не изменяет SQL. Обычные INSERT/UPDATE берут
        ROW EXCLUSIVE, SELECT берет ACCESS SHARE. Вывод содержит режимы блокировки текущей
        транзакции на accounts непосредственно после VALIDATE и до завершающего COMMIT.
        '''}, {'verify_sql.py':sqlcheck}, oracle={'migrations/V2__balance_check.sql':migration_good} if issue else None,
        mutation=None if issue else {'migrations/V2__balance_check.sql':migration_bad},sql=True,
        rubric={'has_issue':issue,'required_issue':'ADD CHECK retains AccessExclusiveLock to transaction end; NOT VALID followed by VALIDATE in the same transaction holds it through the scan.' if issue else None,
          'must_not':['Claim VALIDATE by itself takes AccessExclusiveLock.', 'Require transaction separation when the supplied SQL already commits between phases.', 'Invent absent legacy negative data or a wrapping transaction contrary to the task.']})
    print('Prepared',len(list(TASKS.glob('*/task.json'))),'tasks')


if __name__ == '__main__': main()
