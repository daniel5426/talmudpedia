import type { PricoWidgetBundle } from "./contract";

export type WidgetLabScenario = {
  id: string;
  name: string;
  nameHe: string;
  eyebrow: string;
  eyebrowHe: string;
  description: string;
  descriptionHe: string;
  bundle: PricoWidgetBundle;
  bundleHe: PricoWidgetBundle;
};

export const widgetLabScenarios: WidgetLabScenario[] = [
  {
    id: "atlas-dashboard",
    name: "Atlas Dashboard",
    nameHe: "דשבורד אטלס",
    eyebrow: "Full Bundle",
    eyebrowHe: "חבילה מלאה",
    description: "Dense client overview with KPI, concentration, compare, table, and notes.",
    descriptionHe: "סקירת לקוח מפורטת עם KPI, ריכוז, השוואה, טבלה והערות.",
    bundle: {
      title: "Atlas Medical",
      subtitle: "Current-state dashboard for FX activity and concentration",
      rows: [
        {
          widgets: [
            { kind: "kpi", id: "deals", span: 3, title: "Deals", value: "5" },
            { kind: "kpi", id: "volume", span: 3, title: "Notional Proxy", value: "EUR 1.455M" },
            { kind: "kpi", id: "bank", span: 3, title: "Top Bank", value: 'פועלים-ש"ח' },
            { kind: "kpi", id: "currency", span: 3, title: "Top Currency", value: "EUR 100%" },
          ],
        },
        {
          widgets: [
            {
              kind: "pie",
              id: "bank_mix",
              span: 6,
              title: "Bank Concentration",
              subtitle: "Share of recent notional proxy",
              data: [
                { label: 'פועלים-ש"ח', value: 44.3 },
                { label: "פועלים", value: 24.1 },
                { label: "אוצר החייל", value: 19.2 },
                { label: "ירושלים", value: 12.4 },
              ],
            },
            {
              kind: "bar",
              id: "currency_mix",
              span: 6,
              title: "Currency Concentration",
              subtitle: "Live rows mapped through bank-derived currency data",
              data: [
                { label: "EUR", value: 100 },
                { label: "USD", value: 0 },
              ],
            },
          ],
        },
        {
          widgets: [
            {
              kind: "compare",
              id: "bank_deal_count",
              span: 4,
              title: "Top Two Banks",
              subtitle: "Deal count comparison",
              leftLabel: 'פועלים-ש"ח',
              leftValue: 2,
              rightLabel: "פועלים",
              rightValue: 1,
              delta: "פער של עסקה אחת",
            },
            {
              kind: "note",
              id: "risk",
              span: 8,
              title: "Evidence Notes",
              text: "Notional is proxy-based because direct principal values are sparse. EUR dominates recent activity, and no explicit bank risk flags were returned.",
            },
          ],
        },
        {
          widgets: [
            {
              kind: "table",
              id: "recent",
              span: 12,
              title: "Recent Deal Snapshot",
              columns: ["Date", "Bank", "Currency", "Proxy Notional"],
              rows: [
                ["2026-02-13", 'פועלים-ש"ח', "EUR", "645,000"],
                ["2026-02-13", "פועלים", "EUR", "350,000"],
                ["2026-02-13", "אוצר החייל", "EUR", "280,000"],
                ["2026-02-12", "ירושלים", "EUR", "180,000"],
              ],
            },
          ],
        },
      ],
    },
    bundleHe: {
      title: "אטלס רפואי",
      subtitle: "דשבורד מצב שוטף לפעילות פורקס וריכוז",
      rows: [
        {
          widgets: [
            { kind: "kpi", id: "deals", span: 3, title: "עסקאות", value: "5" },
            { kind: "kpi", id: "volume", span: 3, title: "נוצ'יונל מוערך", value: "EUR 1.455M" },
            { kind: "kpi", id: "bank", span: 3, title: "בנק מוביל", value: 'פועלים-ש"ח' },
            { kind: "kpi", id: "currency", span: 3, title: "מטבע מוביל", value: "EUR 100%" },
          ],
        },
        {
          widgets: [
            {
              kind: "pie",
              id: "bank_mix",
              span: 6,
              title: "ריכוז בנקים",
              subtitle: "חלק מהנוצ'יונל המוערך האחרון",
              data: [
                { label: 'פועלים-ש"ח', value: 44.3 },
                { label: "פועלים", value: 24.1 },
                { label: "אוצר החייל", value: 19.2 },
                { label: "ירושלים", value: 12.4 },
              ],
            },
            {
              kind: "bar",
              id: "currency_mix",
              span: 6,
              title: "ריכוז מטבעות",
              subtitle: "שורות ממופות דרך נתוני מטבע מבנקים",
              data: [
                { label: "EUR", value: 100 },
                { label: "USD", value: 0 },
              ],
            },
          ],
        },
        {
          widgets: [
            {
              kind: "compare",
              id: "bank_deal_count",
              span: 4,
              title: "שני בנקים מובילים",
              subtitle: "השוואת מספר עסקאות",
              leftLabel: 'פועלים-ש"ח',
              leftValue: 2,
              rightLabel: "פועלים",
              rightValue: 1,
              delta: "פער של עסקה אחת",
            },
            {
              kind: "note",
              id: "risk",
              span: 8,
              title: "הערות ראיות",
              text: "הנוצ'יונל מבוסס על פרוקסי מכיוון שערכי קרן ישירים דלילים. EUR שולט בפעילות האחרונה, ולא הוחזרו דגלי סיכון מפורשים לבנק.",
            },
          ],
        },
        {
          widgets: [
            {
              kind: "table",
              id: "recent",
              span: 12,
              title: "תמונת מצב עסקאות אחרונות",
              columns: ["תאריך", "בנק", "מטבע", "נוצ'יונל מוערך"],
              rows: [
                ["2026-02-13", 'פועלים-ש"ח', "EUR", "645,000"],
                ["2026-02-13", "פועלים", "EUR", "350,000"],
                ["2026-02-13", "אוצר החייל", "EUR", "280,000"],
                ["2026-02-12", "ירושלים", "EUR", "180,000"],
              ],
            },
          ],
        },
      ],
    },
  },
  {
    id: "concentration-review",
    name: "Concentration Review",
    nameHe: "סקירת ריכוז",
    eyebrow: "Two-Row Read",
    eyebrowHe: "קריאה דו-שורתית",
    description: "Cleaner analytical composition for side-by-side chart review.",
    descriptionHe: "קומפוזיציה אנליטית נקייה לסקירת גרפים זה לצד זה.",
    bundle: {
      title: "Orion Foods",
      subtitle: "Concentration review for presentation tuning",
      rows: [
        {
          widgets: [
            { kind: "kpi", id: "deals", span: 4, title: "Deals", value: "5" },
            { kind: "kpi", id: "volume", span: 4, title: "Proxy Volume", value: "$1.51M" },
            { kind: "kpi", id: "risk", span: 4, title: "Risk Flag", value: "None" },
          ],
        },
        {
          widgets: [
            {
              kind: "bar",
              id: "banks",
              span: 7,
              title: "Bank Concentration",
              data: [
                { label: "פועלים", value: 38.4 },
                { label: "אוצר החייל", value: 38.4 },
                { label: 'פועלים-ש"ח', value: 23.2 },
              ],
            },
            {
              kind: "note",
              id: "caveat",
              span: 5,
              title: "Caveat",
              text: "Volume uses commission-derived proxy notional. This bundle is useful for tuning chart typography and legend density.",
            },
          ],
        },
      ],
    },
    bundleHe: {
      title: "אוריון מזון",
      subtitle: "סקירת ריכוז לכוונון הצגה",
      rows: [
        {
          widgets: [
            { kind: "kpi", id: "deals", span: 4, title: "עסקאות", value: "5" },
            { kind: "kpi", id: "volume", span: 4, title: "נפח פרוקסי", value: "$1.51M" },
            { kind: "kpi", id: "risk", span: 4, title: "דגל סיכון", value: "ללא" },
          ],
        },
        {
          widgets: [
            {
              kind: "bar",
              id: "banks",
              span: 7,
              title: "ריכוז בנקים",
              data: [
                { label: "פועלים", value: 38.4 },
                { label: "אוצר החייל", value: 38.4 },
                { label: 'פועלים-ש"ח', value: 23.2 },
              ],
            },
            {
              kind: "note",
              id: "caveat",
              span: 5,
              title: "אזהרה",
              text: "הנפח משתמש בנוצ'יונל פרוקסי מבוסס עמלה. חבילה זו שימושית לכוונון טיפוגרפיה ועומס אגדה.",
            },
          ],
        },
      ],
    },
  },
  {
    id: "deal-vs-market",
    name: "Deal vs Market",
    nameHe: "עסקה מול שוק",
    eyebrow: "Compare Focus",
    eyebrowHe: "מיקוד השוואה",
    description: "Narrow layout to tune compare cards and supporting narrative.",
    descriptionHe: "פריסה צרה לכוונון כרטיסי השוואה ונרטיב תומך.",
    bundle: {
      title: "Single Deal Review",
      subtitle: "Compare widget stress test",
      rows: [
        {
          widgets: [
            {
              kind: "compare",
              id: "deal_market",
              span: 6,
              title: "Client Rate vs Market",
              leftLabel: "Client",
              leftValue: 3.92,
              rightLabel: "Market",
              rightValue: 3.71,
              delta: "Client deal is 21 bps above benchmark.",
            },
            {
              kind: "table",
              id: "deal_details",
              span: 6,
              title: "Deal Context",
              columns: ["Deal", "Side", "Currency", "Amount"],
              rows: [["200462", "Buy", "USD/ILS", "1,200,000"]],
            },
          ],
        },
        {
          widgets: [
            {
              kind: "note",
              id: "market_note",
              span: 12,
              title: "Interpretation",
              text: "Useful for styling the compare card as a hero widget with a compact supporting table beneath or beside it.",
            },
          ],
        },
      ],
    },
    bundleHe: {
      title: "סקירת עסקה בודדת",
      subtitle: "בדיקת לחץ לווידג'ט השוואה",
      rows: [
        {
          widgets: [
            {
              kind: "compare",
              id: "deal_market",
              span: 6,
              title: "שער לקוח מול שוק",
              leftLabel: "לקוח",
              leftValue: 3.92,
              rightLabel: "שוק",
              rightValue: 3.71,
              delta: "עסקת הלקוח גבוהה ב-21 נקודות בסיס מהבנצ'מרק.",
            },
            {
              kind: "table",
              id: "deal_details",
              span: 6,
              title: "הקשר עסקה",
              columns: ["עסקה", "צד", "מטבע", "סכום"],
              rows: [["200462", "קנייה", "USD/ILS", "1,200,000"]],
            },
          ],
        },
        {
          widgets: [
            {
              kind: "note",
              id: "market_note",
              span: 12,
              title: "פרשנות",
              text: "שימושי לעיצוב כרטיס ההשוואה כווידג'ט ראשי עם טבלה קומפקטית תומכת לצידו או מתחתיו.",
            },
          ],
        },
      ],
    },
  },
];
