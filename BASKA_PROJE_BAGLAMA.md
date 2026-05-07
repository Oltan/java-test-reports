# Başka Bir Java Projesini Bağlama

Projenizi bu repoya taşımanıza gerek yok. Tek yapmanız gereken `.env` dosyasına projenizin yolunu yazmak.

---

## Nasıl Çalışır

Admin panelinden tag girip "Start" butonuna basınca sistem şunu yapar:

```
cd C:\projects\benim-projem
mvn test -Dcucumber.filter.tags=@2Dpoint -Dretry.count=2
```

Testler bitince `target/allure-results/` klasörünü okur ve sonuçları dashboard'a kaydeder.

---

## Yapılacak Tek Şey — .env Ayarı

`fastapi-server/.env` dosyasına (yoksa `.env.example`'dan kopyalayın) şunu ekleyin:

```env
# Windows
MAVEN_PROJECT_DIR=C:\projects\benim-projem

# Linux / Mac
MAVEN_PROJECT_DIR=/home/user/projects/benim-projem
```

Sonra FastAPI sunucusunu yeniden başlatın:

```bash
uvicorn server:app --reload
```

---

## Proje Gereksinimleri

Projenizin `pom.xml`'inde şunlar olmalı:

**Allure Cucumber entegrasyonu:**
```xml
<dependency>
    <groupId>io.qameta.allure</groupId>
    <artifactId>allure-cucumber7-jvm</artifactId>
    <version>2.27.0</version>
    <scope>test</scope>
</dependency>
```

**Surefire — tag filtresi için:**
```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <systemPropertyVariables>
            <cucumber.filter.tags>${cucumber.filter.tags}</cucumber.filter.tags>
        </systemPropertyVariables>
    </configuration>
</plugin>
```

**`src/test/resources/allure.properties`:**
```properties
allure.results.directory=target/allure-results
```

---

## Kontrol

Admin paneline girin → Tag girin (örn. `@2Dpoint`) → **Start Tests**.

Log'da şunu görmelisiniz:

```
[INFO] Running tests in: C:\projects\benim-projem
mvn test -Dcucumber.filter.tags=@2Dpoint
```

Testler bitince dashboard'da yeni run görünür.
