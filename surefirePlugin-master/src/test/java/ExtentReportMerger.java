import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;

import javax.swing.*;
import java.io.File;
import java.io.FileWriter;

public class ExtentReportMerger {

    public static void main(String[] args) {
        try {
            if (args.length == 2) {
                String outputName = generateOutputName(args[0], args[1]);
                merge(args[0], args[1], outputName);
                JOptionPane.showMessageDialog(null,
                        outputName + " başarıyla oluşturuldu!",
                        "Başarılı", JOptionPane.INFORMATION_MESSAGE);
                return;
            }

            JOptionPane.showMessageDialog(null,
                    "Lütfen ANA raporu seçin (tüm senaryoların olduğu rapor).",
                    "Ana Rapor Seçimi",
                    JOptionPane.INFORMATION_MESSAGE);

            File main = chooseFile();
            if (main == null) return;

            JOptionPane.showMessageDialog(null,
                    "Lütfen TEKRAR ÇALIŞTIRMA raporunu seçin (sadece fail/skip senaryolar).",
                    "Rerun Rapor Seçimi",
                    JOptionPane.INFORMATION_MESSAGE);

            File rerun = chooseFile();
            if (rerun == null) return;

            String outputName = generateOutputName(main.getName(), rerun.getName());
            File output = new File(main.getParent(), outputName);

            merge(main.getAbsolutePath(), rerun.getAbsolutePath(), output.getAbsolutePath());

            JOptionPane.showMessageDialog(null,
                    "Birleştirilmiş rapor oluşturuldu:\n" + output.getAbsolutePath(),
                    "Başarılı",
                    JOptionPane.INFORMATION_MESSAGE);

        } catch (Exception e) {
            e.printStackTrace();
            JOptionPane.showMessageDialog(null,
                    "Hata oluştu: " + e.getMessage(),
                    "Birleştirme Başarısız",
                    JOptionPane.ERROR_MESSAGE);
        }
    }

    private static File chooseFile() {
        JFileChooser chooser = new JFileChooser();
        chooser.setFileFilter(new javax.swing.filechooser.FileNameExtensionFilter(
                "HTML Dosyaları", "html", "htm"));
        int result = chooser.showOpenDialog(null);
        if (result == JFileChooser.APPROVE_OPTION) return chooser.getSelectedFile();
        return null;
    }

    /**
     * Output name example:
     * Input:  Deneme-20251121_045719.html
     * Output: Deneme.html
     */
    private static String generateOutputName(String file1, String file2) {
        String clean1 = stripTimestamp(removeExtension(file1));
        String clean2 = stripTimestamp(removeExtension(file2));

        // If names match, use the shared base
        String prefix = clean1.equals(clean2) ? clean1 : clean1;

        return prefix + ".html";
    }

    private static String removeExtension(String filename) {
        int dot = filename.lastIndexOf('.');
        return (dot == -1) ? filename : filename.substring(0, dot);
    }

    private static String stripTimestamp(String input) {
        // Remove typical timestamp patterns
        String regex = "[-_]?\\d{8}[_-]?\\d{4,6}";
        return input.replaceAll(regex, "").replaceAll("[-_]+$", "");
    }

    private static void merge(String mainFile, String rerunFile, String outputFile) throws Exception {
        Document mainDoc = Jsoup.parse(new File(mainFile), "UTF-8");
        Document rerunDoc = Jsoup.parse(new File(rerunFile), "UTF-8");

        Elements mainTests = mainDoc.select("li.test-item");
        Elements rerunTests = rerunDoc.select("li.test-item");

        java.util.Map<String, Element> rerunMap = new java.util.HashMap<>();
        for (Element test : rerunTests) {
            Element nameTag = test.selectFirst(".test-detail p.name");
            if (nameTag != null) {
                rerunMap.put(nameTag.text().trim(), test);
            }
        }

        for (Element mainTest : mainTests) {
            String status = mainTest.attr("status");

            if (status.equals("fail") || status.equals("skip")) {
                String testName = mainTest.selectFirst(".test-detail p.name").text().trim();

                if (rerunMap.containsKey(testName)) {
                    System.out.println("Güncelleniyor: " + testName);
                    mainTest.replaceWith(rerunMap.get(testName).clone());
                } else {
                    System.out.println("Rerun raporunda bulunamadı, orijinali korunuyor: " + testName);
                }
            } else {
                System.out.println("Başarılı senaryo korunuyor: " +
                        mainTest.selectFirst(".test-detail p.name").text().trim());
            }
        }

        try (FileWriter writer = new FileWriter(outputFile)) {
            writer.write(mainDoc.outerHtml());
        }

        System.out.println("Birleştirilmiş rapor oluşturuldu: " + outputFile);
    }
}
