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
