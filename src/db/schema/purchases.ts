import {
  pgTable,
  uuid,
  text,
  doublePrecision,
  integer,
  timestamp,
} from "drizzle-orm/pg-core";
import { businesses } from "./businesses";
import { parties } from "./parties";
import { products } from "./products";

export const purchases = pgTable("purchases", {
  id: uuid("id").primaryKey().defaultRandom(),
  businessId: uuid("business_id")
    .notNull()
    .references(() => businesses.id, { onDelete: "cascade" }),
  partyId: uuid("party_id").references(() => parties.id, { onDelete: "set null" }),
  referenceNumber: text("reference_number").notNull(),
  status: text("status").notNull().default("completed"), // 'completed' | 'cancelled'
  subtotal: doublePrecision("subtotal").notNull().default(0),
  discountType: text("discount_type").notNull().default("none"), // none | amount | percentage
  discountValue: doublePrecision("discount_value").notNull().default(0), // the % or the flat amount entered
  discountAmount: doublePrecision("discount_amount").notNull().default(0), // resolved currency discount
  tax: doublePrecision("tax").notNull().default(0),
  total: doublePrecision("total").notNull().default(0),
  amountPaid: doublePrecision("amount_paid").notNull().default(0),
  paymentStatus: text("payment_status").notNull().default("unpaid"),
  source: text("source").notNull().default("form"),
  notes: text("notes"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
});

export const purchaseItems = pgTable("purchase_items", {
  id: uuid("id").primaryKey().defaultRandom(),
  purchaseId: uuid("purchase_id")
    .notNull()
    .references(() => purchases.id, { onDelete: "cascade" }),
  productId: uuid("product_id").references(() => products.id, {
    onDelete: "set null",
  }),
  description: text("description").notNull(),
  quantity: integer("quantity").notNull().default(1),
  unitPrice: doublePrecision("unit_price").notNull().default(0),
  lineTotal: doublePrecision("line_total").notNull().default(0),
});

export type Purchase = typeof purchases.$inferSelect;
export type PurchaseItem = typeof purchaseItems.$inferSelect;
