package com.testreports.extent;

import com.aventstack.extentreports.ExtentTest;

/**
 * Thread-local holder so that @After screenshot hooks can retrieve the
 * current scenario's ExtentTest node without being coupled to the plugin.
 */
public final class ExtentTestHolder {

    private static final ThreadLocal<ExtentTest> CURRENT = new ThreadLocal<>();

    private ExtentTestHolder() {}

    static void set(ExtentTest test)   { CURRENT.set(test); }
    static void clear()                { CURRENT.remove(); }

    /** Returns the ExtentTest for the currently executing scenario, or null. */
    public static ExtentTest get()     { return CURRENT.get(); }
}
