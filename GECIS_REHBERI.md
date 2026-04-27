# ExtentReports'tan Allure'a Geçiş Rehberi

Bu rehber, `surefirePlugin-master` içindeki ExtentReports odaklı yapıyı Allure tabanlı raporlama akışına taşımak için hazırlandı. Amaç, mevcut retry, `@id` ve `@dep` davranışlarını korurken rapor üretimini Allure, FastAPI dashboard, Jira, DOORS ve email akışına bağlamaktır.

Örnekler Windows proje yoluna göre verilmiştir:

```text
C:\Users\ol_ta\Desktop\java_reports
```

Geçiş sırasında hedef şudur:

* Cucumber testleri Allure sonucu üretsin.
* Hata anında ekran görüntüsü ve video Allure raporuna eklensin.
* Retry ve senaryo bağımlılık kuralları bozulmasın.
* İstenirse bir süre ExtentReports ve Allure aynı anda çalışsın.
* Son aşamada ExtentReports bağımlılıkları güvenli şekilde kaldırılsın.

## 1. Neden Allure?

| Özellik | ExtentReports | Allure | Kazanan |
|---------|---------------|--------|---------|
| Görsel kalite | Dashboard tipi | Modern, interaktif | Allure |
| Cucumber entegrasyonu | Manuel plugin | Auto (cucumber7-jvm) | Allure |
| History/trend | Yok | Dahili | Allure |
| CI/CD uyumu | Manuel | Jenkins/GH Actions plugin | Allure |
| Screenshot/video | ✅ | ✅ | Berabere |
| Web dashboard | Yok | FastAPI | Allure |
| Jira/DOORS/Email | Yok | Var | Allure |
| **Retry mekanizması** | ✅ (özel) | ⚠️ (taşındı!) | Berabere |
| **@id/@dep** | ✅ | ⚠️ (taşındı!) | Berabere |

Allure bu projede sadece bir HTML raporu değildir. Test çıktısı, hata ekleri, manifest dosyası, FastAPI dashboard, Jira bug açma, DOORS eşleştirme ve email bildirimi aynı zincirin parçalarıdır. ExtentReports daha çok tek koşum raporu üretir. Allure ise geçmiş, trend, ek dosyalar ve CI/CD görünürlüğü için daha uygun bir merkez sağlar.

Önemli karar: Retry ve `@id/@dep` davranışları rapor aracına bağlı kalmamalıdır. Bu nedenle bu özellikler `test-core` tarafına taşınmıştır. Allure'a geçmek bu davranışları kaldırmaz.

## 2. Mevcut Projeye Allure Ekleme, Adım Adım

Bu bölüm, Allure'u mevcut Cucumber projesine eklemek için gereken en küçük kurulumu anlatır. Dosya yollarını kendi proje yapınıza göre uyarlayın. Bu depoda ana çalışma modülü `test-core` modülüdür.

### 2.1 Maven bağımlılığını ekle

`pom.xml` içine Allure Cucumber 7 entegrasyonunu ekleyin. Çok modüllü yapıda bunu testleri koşturan modülün `pom.xml` dosyasına koyun. Bu projede hedef dosya genellikle şudur:

```text
C:\Users\ol_ta\Desktop\java_reports\test-core\pom.xml
```

```xml
<!-- pom.xml'e ekle -->
<dependency>
  <groupId>io.qameta.allure</groupId>
  <artifactId>allure-cucumber7-jvm</artifactId>
  <version>2.25.0</version>
</dependency>
```

Parent POM içinde sürüm yönetimi yapıyorsanız sürümü property olarak da tutabilirsiniz:

```xml
<properties>
  <allure.version>2.25.0</allure.version>
</properties>
```

Sonra dependency içinde şu şekilde kullanabilirsiniz:

```xml
<dependency>
  <groupId>io.qameta.allure</groupId>
  <artifactId>allure-cucumber7-jvm</artifactId>
  <version>${allure.version}</version>
</dependency>
```

### 2.2 Cucumber plugin ayarını yap

`cucumber.properties` dosyasında Allure plugin'i etkinleştirin. Bu dosya genellikle test kaynakları altında durur:

```text
C:\Users\ol_ta\Desktop\java_reports\test-core\src\test\resources\cucumber.properties
```

```properties
# cucumber.properties
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm
```

Eğer mevcut dosyada ExtentReports plugin'i varsa ve tek rapor aracı olarak Allure'a geçmek istiyorsanız ExtentReports plugin sınıfını bu satırdan çıkarın. İki raporu aynı anda üretmek istiyorsanız 4. bölüme bakın.

### 2.3 Allure sonuç klasörünü ayarla

`allure.properties` dosyası yoksa test resources altına ekleyin:

```text
C:\Users\ol_ta\Desktop\java_reports\test-core\src\test\resources\allure.properties
```

```properties
# allure.properties
allure.results.directory=target/allure-results
```

Bu ayar test modülünün çalışma dizinine göre sonuç üretir. `test-core` modülü koşturulduğunda sonuçlar şu klasöre düşer:

```text
C:\Users\ol_ta\Desktop\java_reports\test-core\target\allure-results
```

### 2.4 Testleri koştur ve raporu üret

PowerShell veya CMD içinde proje köküne gidin:

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
mvn -pl test-core test
allure generate --clean test-core\target\allure-results -o test-core\target\allure-report
```

Rapor dosyası burada oluşur:

```text
C:\Users\ol_ta\Desktop\java_reports\test-core\target\allure-report\index.html
```

Tarayıcıda açmak için:

```batch
start "" test-core\target\allure-report\index.html
```

FastAPI dashboard ayrıca şu adreste çalışır:

```text
http://localhost:8000
```

## 3. surefirePlugin Özelliklerini Taşıma

ExtentReports'tan Allure'a geçerken en kritik nokta şudur: Rapor formatı değişir, test koşum davranışı değişmez. `surefirePlugin-master` içinde değerli olan bazı davranışlar artık `test-core` tarafında korunur.

### 3.1 Retry runner

Retry mekanizması `RetryTestRunner.java` ile korunur. Bu sınıf zaten `test-core` tarafına taşınmıştır.

Beklenen davranış:

* Başarısız senaryo belirlenen kurala göre tekrar denenir.
* Son durum Allure sonucuna yansır.
* Ekran görüntüsü ve video hata anında ek olarak saklanır.
* Retry kararları rapor plugin'ine değil runner mantığına bağlıdır.

Kontrol listesi:

* `RetryTestRunner.java` test classpath içinde olmalı.
* Maven test komutu bu runner'ı veya ona bağlı Cucumber ayarını kullanmalı.
* Retry sayısı sistem property, tag veya runner ayarıyla belirleniyorsa eski değerler yeni akışa taşınmalı.

Örnek koşum:

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
mvn -pl test-core test -Dtest=RetryTestRunner
```

### 3.2 Dependency resolver

`@id` ve `@dep` etiketleri `DependencyResolver.java` ile korunur. Bu sınıf da zaten `test-core` tarafına taşınmıştır.

Beklenen davranış:

* `@id:login` gibi kimlikler senaryoyu tanımlar.
* `@dep:login` gibi bağımlılıklar çalışma sırasını veya atlama kararını belirler.
* Bağımlı senaryo, ön koşulu başarısızsa kontrollü şekilde ele alınır.
* Bu karar ExtentReports'a değil Cucumber koşum mantığına bağlıdır.

Örnek etiket kullanımı:

```gherkin
@id:login
Scenario: Kullanıcı sisteme giriş yapar
  Given giriş sayfası açılır
  When geçerli bilgiler girilir
  Then ana sayfa görülür

@id:create-order @dep:login
Scenario: Kullanıcı sipariş oluşturur
  Given kullanıcı oturum açmıştır
  When yeni sipariş oluşturur
  Then sipariş başarıyla kaydedilir
```

### 3.3 Tag runner

Tag bazlı koşum için `scripts\run-by-tag.bat` kullanılır. Bu dosya Windows tarafında hızlı test başlatmak için tutulur.

Örnekler:

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
scripts\run-by-tag.bat @smoke
scripts\run-by-tag.bat @sample-fail
scripts\run-by-tag.bat @id:login
```

Geçişte dikkat edilecekler:

* Tag filtreleri Cucumber tarafında kalır.
* Allure sadece sonuçları toplar.
* Retry ve dependency kararları runner katmanında kalır.
* ExtentReports kaldırıldıktan sonra da tag bazlı koşum devam eder.

### 3.4 ExtentReportMerger durumu

ExtentReports tarafında birden fazla raporu birleştirmek için merger yapısı kullanılmış olabilir. Allure tarafında bu ihtiyaç genellikle `allure-results` klasörlerinin tek rapora dönüştürülmesiyle karşılanır.

Örnek:

```batch
allure generate --clean test-core\target\allure-results -o test-core\target\allure-report
```

Birden fazla modülden sonuç geliyorsa önce sonuç klasörlerini ortak bir klasörde toplayın, sonra Allure raporu üretin.

## 4. Hibrit Kullanım, İkisi Birden

Geçişi tek seferde yapmak zorunda değilsiniz. Bir süre Allure ve ExtentReports aynı Cucumber koşumunda birlikte çalışabilir. Bu yöntem raporları karşılaştırmak, ekip alışkanlıklarını korumak ve rollback ihtiyacını azaltmak için uygundur.

`cucumber.properties` içinde iki plugin'i aynı satırda tanımlayın:

```properties
# cucumber.properties, iki plugin birden!
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm, hooks.ExtentCucumberPlugin
```

Hibrit kullanımda beklenen çıktı:

* Allure sonuçları `target\allure-results` altında oluşur.
* ExtentReports çıktısı mevcut ExtentReports ayarındaki klasöre yazılır.
* Cucumber senaryoları aynı şekilde koşar.
* Retry ve dependency davranışları değişmez.

Dikkat edilmesi gerekenler:

* `hooks.ExtentCucumberPlugin` classpath içinde olmalı.
* Aynı ekran görüntüsü hem Allure hem ExtentReports tarafına ekleniyorsa disk kullanımı artabilir.
* Hibrit mod kalıcı çözüm değil, geçiş dönemi aracıdır.
* CI/CD çıktısında hangi raporun ana kaynak olduğu açıkça belirtilmelidir.

Önerilen hibrit süre:

* İlk hafta iki raporu birlikte üretin.
* Hatalı senaryolarda eklerin iki tarafta da göründüğünü kontrol edin.
* Retry ve `@id/@dep` akışını örnek feature dosyalarıyla doğrulayın.
* Ekip Allure linklerini kullanmaya başladıktan sonra ExtentReports'u kaldırın.

## 5. ExtentReports'u Tamamen Kaldırma

Allure raporları, FastAPI dashboard ve özel runner davranışları doğrulandıktan sonra ExtentReports bağımlılıkları kaldırılabilir.

### 5.1 POM temizliği

Ana `pom.xml` ve modül `pom.xml` dosyalarında şu parçaları kaldırın:

* `com.aventstack` ExtentReports bağımlılıkları.
* `extent-integration` modül bağımlılığı.
* Parent POM içindeki `extent-integration` module kaydı.
* Sadece ExtentReports için kullanılan plugin veya resource ayarları.

Korunması gerekenler:

* `allure-cucumber7-jvm`
* `allure-junit-platform`, projede kullanılıyorsa
* `allure-integration`
* `report-model`
* `test-core`

### 5.2 Cucumber ayarını sadeleştir

Önceki hibrit ayar:

```properties
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm, hooks.ExtentCucumberPlugin
```

Son Allure ayarı:

```properties
cucumber.plugin=io.qameta.allure.cucumber7jvm.AllureCucumber7Jvm
```

### 5.3 ExtentReports modülünü kaldır

Kod temizliği için şu klasörler ve dosyalar gözden geçirilir:

```text
C:\Users\ol_ta\Desktop\java_reports\extent-integration
C:\Users\ol_ta\Desktop\java_reports\surefirePlugin-master
```

`extent-integration` aktif Maven modülüyse kaldırmadan önce parent POM içindeki module kaydını silin. Sonra klasörü kaldırabilirsiniz.

CMD örneği:

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
rmdir /s /q extent-integration
```

`surefirePlugin-master` ayrı bir proje olduğu için hemen silmek yerine arşivlemek daha güvenlidir. Yeni koşumlar Allure ile doğrulandıktan sonra bu klasör pasif tutulabilir.

### 5.4 Kaldırma sonrası doğrulama

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
mvn validate
mvn -pl test-core test
allure generate --clean test-core\target\allure-results -o test-core\target\allure-report
start "" test-core\target\allure-report\index.html
```

Doğrulamada bakılacak noktalar:

* Testler çalışıyor mu?
* Allure raporu oluşuyor mu?
* Başarısız senaryoda ekran görüntüsü ve video ekleri görünüyor mu?
* Retry beklenen sayıda çalışıyor mu?
* `@id/@dep` senaryoları eski sırayla ve eski kuralla işleniyor mu?
* FastAPI dashboard test run verisini gösteriyor mu?

## 6. Windows'ta Çalıştırma

Bu rehber Windows kullanımını temel alır. Komutları PowerShell veya CMD üzerinden çalıştırabilirsiniz.

### 6.1 Tek tıkla kurulum

Proje kökünde kurulum dosyası varsa çalıştırın:

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
setup.bat
```

`setup.bat` beklenen görevleri yapar:

* Gerekli klasörleri hazırlar.
* Ortam ayarlarını kontrol eder.
* Bağımlılık kurulumunu başlatır.
* Windows tarafında hızlı başlangıç sağlar.

### 6.2 Sunucuyu başlat

FastAPI dashboard için:

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
start-server.bat
```

Eğer batch dosyası `scripts` klasöründeyse:

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
scripts\start-server.bat
```

Tarayıcı adresi:

```text
http://localhost:8000
```

Varsayılan giriş bilgileri:

```text
Kullanıcı adı: admin
Şifre: admin123
```

### 6.3 Tag ile test koş

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
scripts\run-by-tag.bat @smoke
```

Örnek tag değerleri:

```batch
scripts\run-by-tag.bat @sample-fail
scripts\run-by-tag.bat @regression
scripts\run-by-tag.bat @id:login
```

### 6.4 Allure raporu üret

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
allure generate --clean test-core\target\allure-results -o test-core\target\allure-report
start "" test-core\target\allure-report\index.html
```

### 6.5 Günlük kullanım sırası

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
setup.bat
start-server.bat
scripts\run-by-tag.bat @smoke
allure generate --clean test-core\target\allure-results -o test-core\target\allure-report
start "" test-core\target\allure-report\index.html
```

Her gün `setup.bat` çalıştırmak şart değildir. Kurulum tamamlandıysa genellikle şu sıra yeterlidir:

```batch
cd /d C:\Users\ol_ta\Desktop\java_reports
start-server.bat
scripts\run-by-tag.bat @smoke
allure generate --clean test-core\target\allure-results -o test-core\target\allure-report
```

## 7. Sık Sorulan Sorular

### Retry mekanizmam bozulur mu?

Hayır. Retry davranışı ExtentReports plugin'ine bağlı değildir. `RetryTestRunner.java` `test-core` tarafına taşındığı için Allure'a geçişte korunur. Rapor formatı değişir, tekrar deneme mantığı aynı kalır.

### `@id/@dep` çalışmaya devam eder mi?

Evet. `DependencyResolver.java` `test-core` tarafına taşındığı için `@id` ve `@dep` etiketleri çalışmaya devam eder. Allure bu etiketleri raporda gösterebilir, fakat bağımlılık kararını runner katmanı verir.

### Performans farkı var mı?

Evet, Allure tarafı genellikle daha hızlı ve daha sade çalışır. Cucumber 7 entegrasyonu hazır plugin ile gelir. Manuel event listener yazma ihtiyacı azalır. ExtentReports ile aynı anda çalıştırılan hibrit modda ise iki rapor üretildiği için disk kullanımı ve toplam süre artabilir.

### Raporlarım nerede?

Allure HTML raporu burada oluşur:

```text
C:\Users\ol_ta\Desktop\java_reports\test-core\target\allure-report\index.html
```

Allure ham sonuçları burada oluşur:

```text
C:\Users\ol_ta\Desktop\java_reports\test-core\target\allure-results
```

Web dashboard burada açılır:

```text
http://localhost:8000
```

### ExtentReports'u hemen silmeli miyim?

Hayır. Önce hibrit modda iki raporu birlikte üretin. Kritik senaryolarda Allure eklerinin, retry davranışının ve `@id/@dep` akışının doğru olduğunu görün. Sonra ExtentReports bağımlılıklarını kaldırın.

### Allure tek başına retry yapar mı?

Hayır, Allure esas olarak raporlama aracıdır. Retry davranışı test runner katmanında kalmalıdır. Bu projede bu görev `RetryTestRunner.java` ile çözülür.

### Screenshot ve video ekleri kaybolur mu?

Hayır. `allure-integration` modülündeki hook yapısı hata anında ekran görüntüsü ve video eklerini Allure sonucuna bağlar. Başarılı senaryolarda video saklamama kuralı korunabilir.

### Jira, DOORS ve email akışı ExtentReports'a bağlı mı?

Hayır. Bu akışlar Allure sonuçları, manifest dosyaları ve FastAPI dashboard ile birlikte çalışır. ExtentReports kaldırıldığında Jira, DOORS ve email entegrasyonlarının rapor zincirinde kalması beklenir.

### Eski ExtentReports çıktıları ne olacak?

Eski HTML dosyalarını arşiv olarak saklayabilirsiniz. Yeni koşumların ana kaynağı Allure raporu ve FastAPI dashboard olmalıdır.

### CI/CD içinde hangi rapor yayınlanmalı?

Geçiş döneminde iki rapor da yayınlanabilir. Kalıcı durumda Allure raporu ana rapor olmalıdır. Dashboard linki ve Allure HTML çıktısı build sonucuna eklenmelidir.

## Geçiş Kontrol Listesi

| Kontrol | Durum |
|---------|-------|
| `allure-cucumber7-jvm` dependency eklendi | ☐ |
| `cucumber.properties` Allure plugin ile güncellendi | ☐ |
| `allure.properties` oluşturuldu | ☐ |
| `RetryTestRunner.java` ile retry doğrulandı | ☐ |
| `DependencyResolver.java` ile `@id/@dep` doğrulandı | ☐ |
| `scripts\run-by-tag.bat` ile tag koşumu doğrulandı | ☐ |
| Hibrit modda rapor karşılaştırması yapıldı | ☐ |
| ExtentReports dependency kayıtları kaldırıldı | ☐ |
| `extent-integration` modülü kaldırıldı veya pasif edildi | ☐ |
| Allure raporu üretildi | ☐ |
| FastAPI dashboard çalıştı | ☐ |

## Önerilen Son Durum

Son durumda proje şu akışla çalışmalıdır:

```text
Cucumber testleri
Allure results
Allure HTML report
Run manifest
FastAPI dashboard
Jira, DOORS, email entegrasyonları
```

Bu yapıda ExtentReports sadece eski rapor arşivleri veya geçici karşılaştırma için kalır. Yeni raporlama zincirinin ana kaynağı Allure olur.
