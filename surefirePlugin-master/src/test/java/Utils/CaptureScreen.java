package Utils;

import org.apache.commons.io.FileUtils;
import org.openqa.selenium.OutputType;
import org.openqa.selenium.TakesScreenshot;
import org.openqa.selenium.WebDriver;

import java.io.File;
import java.io.IOException;

public class CaptureScreen {

    public static String captureAsBase64(WebDriver driver) {
        return ((TakesScreenshot) driver).getScreenshotAs(OutputType.BASE64);
    }

    public static String captureToFile(WebDriver driver, String captureScreen) {
        File srcFile = ((TakesScreenshot) driver).getScreenshotAs(OutputType.FILE);
        File destFile = new File("target/screenshots/" + captureScreen);
        destFile.getParentFile().mkdirs();
        try {
            FileUtils.copyFile(srcFile, destFile);
        } catch (IOException e) {
            e.printStackTrace();
        }
        System.out.println("Screenshot was successfully saved");
        return destFile.getAbsoluteFile().toString();
    }
}


