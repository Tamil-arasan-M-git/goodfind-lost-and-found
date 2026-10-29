export function validateReportForm(form) {
  const errors = {};
  if (!form.item_name.trim()) errors.item_name = "Enter an item name so others can recognize it.";
  if (!form.category.trim()) errors.category = "Choose or enter a category.";
  if (!form.item_date) errors.item_date = "Choose the date the item was lost or found.";
  if (!form.location.trim()) errors.location = "Enter a general location, such as a building or transit stop.";
  return errors;
}

export function displayLabel(label) {
  return label.replaceAll("_", " ");
}

export const REPORT_CATEGORY_VALUES = Object.freeze([
  "electronics", "clothing", "documents", "accessories", "books", "other",
]);

export const REPORT_CATEGORY_OPTIONS = Object.freeze([
  { value: "electronics", label: "Electronics" },
  { value: "clothing", label: "Clothing" },
  { value: "documents", label: "Documents" },
  { value: "accessories", label: "Accessories" },
  { value: "books", label: "Books" },
  { value: "other", label: "Other" },
]);

const DETECTION_CATEGORY_MAP = Object.freeze({
  mobile_phone: "electronics",
  backpack_bag: "accessories",
  keys: "accessories",
  wallet_purse: "accessories",
  water_bottle: "other",
});

export function getCategorySuggestions(detections, supportedCategories = REPORT_CATEGORY_VALUES) {
  const allowed = new Set(supportedCategories);
  const suggestions = new Map();
  for (const detection of Array.isArray(detections) ? detections : []) {
    const category = DETECTION_CATEGORY_MAP[detection?.label];
    if (category && allowed.has(category)) {
      const labels = suggestions.get(category) || [];
      if (!labels.includes(detection.label)) labels.push(detection.label);
      suggestions.set(category, labels);
    }
  }
  return [...suggestions].map(([value, labels]) => ({ value, labels }));
}
