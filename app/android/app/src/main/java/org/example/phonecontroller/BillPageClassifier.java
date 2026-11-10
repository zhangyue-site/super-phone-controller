package org.example.phonecontroller;

import java.util.regex.Pattern;

/** Recognize the bill list from its controls, rather than a mention of bills. */
final class BillPageClassifier {
    private static final Pattern MONTH = Pattern.compile("(?:1[0-2]|[1-9])月");

    private BillPageClassifier() {}

    static String classify(String compactText, boolean hasAmount) {
        if (compactText.contains("本地模型工作台")
                || (compactText.contains("被控手机")
                    && (compactText.contains("无障碍辅助定位")
                        || compactText.contains("停止控制与共享")))) {
            return "other";
        }
        if (compactText.contains("阿柴记账") && compactText.contains("保存")
                && compactText.contains("取消")) {
            return "achai";
        }
        if (!hasAmount || !compactText.contains("筛选")) {
            return "other";
        }

        int tabs = 0;
        for (String tab : new String[]{"全部", "转账", "退款", "订单"}) {
            if (compactText.contains(tab)) {
                tabs++;
            }
        }
        boolean hasSearch = compactText.contains("搜索交易记录");
        boolean hasMonthlySummary = MONTH.matcher(compactText).find()
                && compactText.contains("收入") && compactText.contains("支出")
                && compactText.contains("收支分析");
        return (hasSearch && tabs >= 2) || (hasMonthlySummary && tabs >= 2)
                ? "bill" : "other";
    }
}
