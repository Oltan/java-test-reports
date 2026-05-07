# Sürüm ve Ortam Bilgisinin Rapora Yansıtılması

Dashboard'da her run için "sürüm" ve "ortam" alanları görünür. Bu değerlerin dolu gelmesi için
iki ayrı yol vardır: **Java'dan API'ye göndermek** veya **Allure `environment.properties`
dosyasını otomatik oluşturmak**.

---

## Yöntem 1 — Java'dan API'ye parametre göndermek (önerilen)

`TestReportClient` veya doğrudan HTTP çağrısında `version` ve `environment` alanlarını doldurun:

```java
// Sistem değişkeni yoksa "dev" varsayılan değer kullanılır
String version = System.getProperty("app.version", "dev");
String env     = System.getProperty("app.env", "local");

TestRunOptions options = new TestRunOptions();
options.setVersion(version);
options.setEnvironment(env);
options.setVisibility("public");
apiClient.submitRun(runId, options);
```

Maven'dan çalıştırırken:
```bash
mvn test -Dapp.version=1.4.2 -Dapp.env=staging
```

CI/CD'de (GitHub Actions örneği):
```yaml
- name: Run tests
  run: mvn test -Dapp.version=${{ github.ref_name }} -Dapp.env=staging
```

---

## Yöntem 2 — Allure `environment.properties` (fallback / otomatik)

Server, `options.version` boş gelirse otomatik olarak
`test-core/target/allure-results/environment.properties` dosyasına bakar.

Allure bu dosyayı rapora ekler ve server oradan `VERSION` anahtarını okur.

### 2a — Maven Surefire ile otomatik oluştur

`test-core/pom.xml` surefire `<configuration>` bloğuna ekleyin:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <!-- mevcut <includes> bloğu burada kalır -->
    <systemPropertyVariables>
      <allure.results.directory>target/allure-results</allure.results.directory>
    </systemPropertyVariables>
  </configuration>
</plugin>
```

Ve testlerin başında (örn. `@BeforeAll` veya Allure listener'da) dosyayı yazın:

```java
import io.qameta.allure.AllureLifecycle;
import io.qameta.allure.model.Parameter;
import java.nio.file.*;
import java.util.Properties;

// src/test/java/com/testreports/allure/AllureEnvironmentWriter.java
public class AllureEnvironmentWriter {
    public static void write() throws Exception {
        Properties props = new Properties();
        props.setProperty("VERSION",     System.getProperty("app.version", "dev"));
        props.setProperty("ENVIRONMENT", System.getProperty("app.env", "local"));
        props.setProperty("BRANCH",      System.getProperty("git.branch", "unknown"));

        Path dir = Paths.get("target/allure-results");
        Files.createDirectories(dir);
        try (var out = Files.newOutputStream(dir.resolve("environment.properties"))) {
            props.store(out, null);
        }
    }
}
```

`CucumberTestRunner`'ı kullanan herhangi bir `@BeforeAll`'da (veya ayrı bir JUnit 5 extension'da)
çağırın:

```java
@BeforeAll
static void setupAllure() throws Exception {
    AllureEnvironmentWriter.write();
}
```

### 2b — `environment.properties` formatı

Server yalnızca `VERSION=` anahtarını okur. Diğer anahtarlar Allure raporunda görünür ama
server tarafından kullanılmaz.

```properties
VERSION=1.4.2
ENVIRONMENT=staging
BRANCH=release/1.4
BUILD_NUMBER=42
```

---

## Öncelik sırası

```
options.version (Java API çağrısı)
  └── boşsa → allure-results/environment.properties → VERSION=
        └── o da yoksa → "" (dashboard'da boş görünür)
```

---

## Retry ve allure-results temizliği

`RetryTestRunner` tek bir Maven invocation içinde birden fazla `Main.run()` çağrısı yapar;
her çağrı aynı `historyId`'ye sahip yeni bir result dosyası üretir. Server bu dosyaları
doğru şekilde "aynı senaryonun retry denemeleri" olarak gruplar.

**Önemli:** allure-results dizini Maven tarafından **otomatik temizlenmez**.
Eski run'lardan kalan dosyalar birikmemesi için:

```bash
# Option A — mvn clean kullan (target/ hepsini siler)
mvn clean test

# Option B — sadece allure-results'ı temizle
rm -rf test-core/target/allure-results
mvn test
```

Ya da `pom.xml`'de surefire'a temizleme komutu ekle:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-clean-plugin</artifactId>
  <executions>
    <execution>
      <id>clean-allure-results</id>
      <phase>initialize</phase>
      <goals><goal>clean</goal></goals>
      <configuration>
        <filesets>
          <fileset>
            <directory>target/allure-results</directory>
            <includes><include>**/*-result.json</include></includes>
          </fileset>
        </filesets>
      </configuration>
    </execution>
  </executions>
</plugin>
```

> Server zaten "son 24 saatin" sonuçlarına bakarak birikmiş eski dosyaları filtreler,
> ama kesin güvence için temizlik tercih edilmeli.

---

## Hızlı kontrol

Test çalıştıktan sonra şu dosya var mı?
```
test-core/target/allure-results/environment.properties
```

Varsa içeriği doğrula:
```bash
cat test-core/target/allure-results/environment.properties
# VERSION=1.4.2
# ENVIRONMENT=staging
```

Dashboard'da run'ın sürüm sütunu doluysa yapılandırma doğrudur.
