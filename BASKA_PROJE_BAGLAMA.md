# Başka Bir Java Projesini Bağlama

Admin panelinden tag girip test başlatmak istiyorsanız, yeni projenizin bu repoya Maven modülü olarak bağlanması gerekir.

---

## Nasıl Çalışır

Admin panelinde "Tag" alanına `@smoke` gibi bir şey girip "Start" butonuna basınca sistem şu komutu çalıştırır:

```
mvn -pl <MAVEN_MODULE> test -Dcucumber.filter.tags=@smoke
```

Bu komut **bu reponun kök dizininden** (`java-test-reports/`) çalışır. Yani yeni projeniz bu reponun içinde bir Maven modülü olmalıdır.

---

## Adım 1 — Projeyi Bu Repoya Ekleyin

Yeni projenizin klasörünü reponun köküne kopyalayın:

```
java-test-reports/
├── test-core/          ← mevcut proje
├── benim-projem/       ← yeni proje buraya
│   ├── pom.xml
│   └── src/
└── pom.xml             ← kök pom.xml'e modül olarak ekleyin
```

Kök `pom.xml`'e modülü bildirin:

```xml
<modules>
    <module>test-core</module>
    <module>benim-projem</module>   <!-- ekleyin -->
</modules>
```

---

## Adım 2 — Yeni Projenin pom.xml Gereksinimleri

Projenizin `pom.xml`'inde şunlar olmalı:

```xml
<!-- Cucumber runner için -->
<dependency>
    <groupId>io.cucumber</groupId>
    <artifactId>cucumber-java</artifactId>
    <version>7.18.0</version>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>io.cucumber</groupId>
    <artifactId>cucumber-junit</artifactId>
    <version>7.18.0</version>
    <scope>test</scope>
</dependency>

<!-- Allure raporlama için -->
<dependency>
    <groupId>io.qameta.allure</groupId>
    <artifactId>allure-cucumber7-jvm</artifactId>
    <version>2.27.0</version>
    <scope>test</scope>
</dependency>
```

Surefire plugin'inde Cucumber tag filtresi için sistem property'sini geçirin:

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

---

## Adım 3 — allure.properties

Projenizde `src/test/resources/allure.properties` dosyası oluşturun:

```properties
allure.results.directory=target/allure-results
```

---

## Adım 4 — .env Dosyasına MAVEN_MODULE Ekleyin

`java-test-reports/fastapi-server/.env` (veya `java-test-reports/.env`) dosyasına:

```env
MAVEN_MODULE=benim-projem
```

Klasör adı ne ise onu yazın. Tanımlanmazsa sistem varsayılan olarak `test-core` kullanır.

---

## Adım 5 — Sunucuyu Yeniden Başlatın

```bash
# FastAPI sunucusunu durdurup yeniden başlatın
cd fastapi-server
uvicorn server:app --reload
```

---

## Kontrol

Admin paneline girin → Tag alanına projenizde var olan bir tag'i yazın (örn. `@regression`) → **Start Tests** butonuna basın.

Logda şunu görmelisiniz:

```
mvn -pl benim-projem test -Dcucumber.filter.tags=@regression
```
