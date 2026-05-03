# Test Raporlama Sistemi, Kullanım Rehberi

Bu rehber mühendis akışını adım adım gösterir. Ekran görüntüleri T23 kanıt setinden gelir ve `.sisyphus/evidence/` altında saklanır. Bağlantılar göreli olarak `../.sisyphus/evidence/task-23-*.png` biçimini kullanır.

Görüntülerde parola, token, Jira kişisel anahtarı, SMTP parolası veya DOORS erişim bilgisi bulunmamalı. Login sırasında kendi mühendis hesabını kullan. Ortak parola ya da gizli değerleri dokümana yazma.

## 1. Sunucuyu başlat

Windows PowerShell veya CMD içinde:

```bash
wsl bash /mnt/c/Users/ol_ta/desktop/java_reports/start.sh
```

WSL terminali içinden çalışıyorsan:

```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports && bash start.sh
```

Terminal açık kalmalı. Sunucu durursa dashboard, triage ve public rapor sayfaları da kapanır.

## 2. Tarayıcı adresleri

Ana dashboard:

```text
http://localhost:8000
```

API dokümanı:

```text
http://localhost:8000/docs
```

Örnek triage sayfası:

```text
http://localhost:8000/reports/live-demo-001/triage
```

`localhost` açılmazsa PowerShell içinde WSL IP değerini al:

```bash
wsl hostname -I
```

Sonra tarayıcıda şu biçimi kullan:

```text
http://172.x.x.x:8000
```

## 3. Mühendis Girişi

Mühendis hesabı dashboard ve işlem sayfaları için gereklidir. Public rapor bağlantısı ise giriş istemez.

1. Dashboard adresini aç.
2. Giriş formunda mühendis kullanıcı adını yaz.
3. Parolayı ekran görüntüsüne sokmadan gir.
4. Giriş başarılı olunca dashboard kartları ve işlem bağlantıları görünür.

![Mühendis giriş formu](../.sisyphus/evidence/task-23-01-engineer-login.png)

![Giriş sonrası mühendis dashboard görünümü](../.sisyphus/evidence/task-23-02-engineer-dashboard.png)

Mühendis sınırı burada başlar. Test başlatma, triage, Jira işlemleri, DOORS ve email butonları sadece giriş yapan kullanıcıya açıktır. Public rapor sayfası yalnızca paylaşılmış rapor sonucunu gösterir, yönetim işlemi yaptırmaz.

## 4. Test Çalıştırma

Test başlatma sayfasında çalışma parametrelerini seç. Bu bölüm Cucumber ve Allure çıktısını üretir.

1. Dashboard üzerinden test çalıştırma sayfasına git.
2. Çalıştırılacak tag veya paket seçimini yap.
3. Parallel alanına aynı anda kaç senaryo koşacağını yaz.
4. Retry alanına başarısız senaryonun kaç kez tekrar deneneceğini yaz.
5. Başlat düğmesine bas.
6. İş bitince run manifest, Allure sonuçları ve dashboard özeti güncellenir.

![Test çalıştırma yönetim sayfası](../.sisyphus/evidence/task-23-03-admin-test-page.png)

![Parallel ve retry alanları](../.sisyphus/evidence/task-23-04-parallel-retry-fields.png)

Parallel değeri makine kapasitesine göre seçilmeli. Retry değeri hatalı testleri gizlemek için değil, geçici ortam sorunlarını ayıklamak için kullanılmalı.

## 5. Triage ve Jira

Triage sayfası başarısız senaryoları inceler. Burada hata sebebi, ekran görüntüsü, video bağlantısı, Jira durumu ve override kararı birlikte görülür.

1. Run detayından Triage bağlantısını aç.
2. Başarısız senaryonun hata mesajını ve eklerini incele.
3. Gerçek ürün hatasıysa Jira butonuyla kayıt oluştur ya da var olan kayıtla eşleştir.
4. Test verisi, ortam veya otomasyon hatasıysa override butonuyla not ekle.
5. Karar notunu kısa, açık ve izlenebilir yaz.

![Triage sayfası ve hata kartları](../.sisyphus/evidence/task-23-05-triage-page.png)

![Jira ve override butonları](../.sisyphus/evidence/task-23-06-jira-override-actions.png)

Jira butonu mühendis yetkisi ister. Public kullanıcı bu butonu göremez ve Jira durumunu değiştiremez. Override işlemi de yalnızca giriş yapan kullanıcıya açıktır.

## 6. Rapor Oluşturma

Rapor oluşturma adımı birden fazla run sonucunu birleştirir ve paylaşılacak görünümü hazırlar.

1. Merge veya rapor oluşturma sayfasını aç.
2. Birleştirilecek run kayıtlarını seç.
3. Senaryo seçimi bölümünde rapora girecek senaryoları işaretle.
4. Oluştur düğmesine bas.
5. Paylaşım bağlantısı üretildiyse kopyala.

![Rapor birleştirme sayfası](../.sisyphus/evidence/task-23-07-merge-page.png)

![Senaryo seçim ekranı](../.sisyphus/evidence/task-23-08-scenario-selection.png)

![Public paylaşım bağlantısı](../.sisyphus/evidence/task-23-09-public-share-url.png)

Paylaşım bağlantısı sadece rapor okumak içindir. Bu bağlantıyla test başlatılamaz, Jira kaydı açılamaz, override yapılamaz, DOORS veya email işlemi çalıştırılamaz.

## 7. Public Rapor

Public rapor sayfası dış paylaşıma uygun dar görünüm sağlar. Amaç, sonuçları göstermek ve gizli alanları saklamaktır.

Public sayfada bulunabilecek bilgiler:

1. Run adı ve zaman bilgisi.
2. Toplam, geçen ve kalan senaryo sayıları.
3. Senaryo adı, durum ve kısa hata özeti.
4. Gizli bilgi içermeyen rapor ekleri.

Public sayfada bulunmaması gereken bilgiler:

1. Token, parola veya oturum bilgisi.
2. Jira kişisel anahtarı ve tam yetkili işlem butonları.
3. DOORS erişim bilgisi.
4. SMTP ayarı, alıcı listesi ve gizli ortam değeri.
5. Ham artifact indirme bağlantısı, bu bağlantı yetkisiz kullanıcıya açılmamalı.

![Public rapor sayfası](../.sisyphus/evidence/task-23-10-public-report.png)

## 8. DOORS ve Email

DOORS ve email adımı rapor sonucunu ilgili ekiplerle paylaşır. Bu işlem mühendis girişi gerektirir.

1. Rapor veya pipeline sayfasında DOORS butonunu bul.
2. Gereksinim eşleştirmesini kontrol et.
3. DOORS aktarımını çalıştır.
4. Email butonuyla rapor özetini gönder.
5. Gönderim sonucunu ekranda ve loglarda kontrol et.

![DOORS ve email butonları](../.sisyphus/evidence/task-23-11-doors-email-buttons.png)

Email metninde gizli değer yazma. DOORS aktarımı da yalnızca gerekli senaryo, gereksinim ve durum bilgisini taşımalı.

## 9. Hızlı kontrol listesi

1. Sunucu çalışıyor.
2. Mühendis hesabıyla giriş yapıldı.
3. Parallel ve retry değerleri seçildi.
4. Test çalışması tamamlandı.
5. Triage kararları Jira veya override ile kaydedildi.
6. Rapor birleştirildi ve senaryo seçimi yapıldı.
7. Public bağlantı sadece okuma sınırında test edildi.
8. DOORS ve email işlemleri yetkili kullanıcıyla çalıştırıldı.
9. Ekran görüntülerinde gizli bilgi bulunmadığı kontrol edildi.
