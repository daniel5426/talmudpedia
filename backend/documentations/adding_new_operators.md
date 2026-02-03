# Adding New Operators

This guide explains the process of adding a new operator to the RAG Pipeline platform. Our platform uses a **Contract-Driven Architecture** where every operator consists of a **Specification (Spec)** and an **Executor**.

---

## 1. Backend Implementation

### Step A: Define the Operator Specification
Operators are defined in `backend/app/rag/pipeline/registry.py`. You must add your operator to the appropriate category dictionary (e.g., `TRANSFORM_OPERATORS`, `RETRIEVAL_OPERATORS`, etc.).

```python
# Example: Adding a new Text Translator operator
"text_translator": OperatorSpec(
    operator_id="text_translator",
    display_name="Text Translator",
    category=OperatorCategory.TRANSFORM,
    version="1.0.0",
    description="Translates text between languages",
    input_type=DataType.NORMALIZED_DOCUMENTS,
    output_type=DataType.NORMALIZED_DOCUMENTS,
    required_config=[
        ConfigFieldSpec(
            name="target_language",
            field_type=ConfigFieldType.SELECT,
            options=["en", "he", "fr", "es"],
            required=True,
            description="The language to translate to"
        ),
    ],
    tags=["nlp", "translation"],
)
```

**Key Fields:**
- `operator_id`: Unique identifier used by the engine.
- `input_type` / `output_type`: Defines compatibility with other nodes (Type Safety).
- `required_config`: Fields the user *must* fill in the UI.

### Step B: Create the Executor
Executors live in `backend/app/rag/pipeline/operator_executor.py`. Create a class that inherits from `OperatorExecutor`.

```python
class TextTranslatorExecutor(OperatorExecutor):
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        # 1. Get config
        target_lang = context.config.get("target_language", "en")
        
        # 2. Process data
        documents = input_data.data
        translated_docs = []
        
        for doc in documents:
            # Your logic here...
            translated_docs.append(translate(doc, target_lang))
            
        # 3. Return results
        return OperatorOutput(
            operator_id=self.spec.operator_id,
            data=translated_docs,
            success=True
        )
```

### Step C: Register the Executor
In `backend/app/rag/factory.py` (or the dispatcher within `operator_executor.py`), ensure the new executor is mapped to its `operator_id`.

---

## 2. Frontend Implementation

To make the operator visible and functional in the Builder UI, follow these steps in `frontend/src/components/pipeline/`.

### Step A: Update Category & Types (If needed)
If you created a new category or data type, add it to `types.ts`:
- `OperatorCategory`: Add the new category string.
- `DataType`: Add the new data type string.
- `CATEGORY_COLORS`: Define a CSS variable for the node color.

### Step B: Map Component Type
Update `nodes/index.ts` to tell ReactFlow which visual component to use for your category:

```typescript
export const nodeTypes = {
  // ...
  translation: TransformNode, // Use TransformNode for most processing tasks
}
```

### Step C: Add Category Icon
Update `nodes/BaseNode.tsx` to map an icon from `lucide-react`:

```typescript
const CATEGORY_ICONS: Record<string, React.ElementType> = {
  // ...
  translation: Languages, 
}
```

### Step D: Update Catalog Visibility
In `NodeCatalog.tsx`, ensure your new category is included in the `categories` list for the relevant pipeline type:

```typescript
const categories = useMemo(() => {
  if (pipelineType === "ingestion") {
    return ["source", "normalization", "translation", "storage"]; // Add it here
  }
  // ...
}, [pipelineType]);
```

---

## Summary Checklist
- [ ] Added `OperatorSpec` to `registry.py`
- [ ] Added `OperatorExecutor` to `operator_executor.py`
- [ ] Connected Spec to Executor in the Factory
- [ ] (Frontend) Added category/icon to `BaseNode.tsx`
- [ ] (Frontend) Updated `nodeTypes` in `nodes/index.ts`
- [ ] (Frontend) Verified visibility in `NodeCatalog.tsx`
