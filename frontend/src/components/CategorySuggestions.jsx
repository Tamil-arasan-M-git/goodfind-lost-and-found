import { displayLabel } from "../reportForm";

function CategorySuggestions({ suggestions, onUse }) {
  if (!suggestions.length) return null;

  return <div className="category-suggestions" role="status" aria-live="polite">
    <strong>AI category suggestion{suggestions.length > 1 ? "s" : ""}</strong>
    {suggestions.map((suggestion) => <div className="category-suggestion" key={suggestion.value}>
      <span><b>{displayLabel(suggestion.value)}</b> based on {suggestion.labels.map(displayLabel).join(", ")}</span>
      <button type="button" className="text-button" onClick={() => onUse(suggestion.value)}>Use suggested category</button>
    </div>)}
    <small>Suggestions are optional. Your selected category is never changed unless you choose one.</small>
  </div>;
}

export default CategorySuggestions;
