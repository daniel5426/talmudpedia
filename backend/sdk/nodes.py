from typing import Dict, Any, List, Optional
import json

class Node:
    """Base class for a dynamic pipeline node."""
    def __init__(
        self, 
        node_type: str, 
        config: Dict[str, Any] = None, 
        spec: Dict[str, Any] = None,
        node_id: Optional[str] = None
    ):
        self.node_type = node_type
        self.config = config or {}
        self.spec = spec or {}
        self.id = node_id  # Assigned when added to pipeline usually
        self.category = self.spec.get("category", "unknown")
        
        # Validation could happen here
        # self._validate_config()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize definition for API."""
        return {
            "id": self.id,
            "operator": self.node_type,
            "category": self.category,
            "config": self.config,
            # Position is often required by visual builders but irrelevant for logic.
            # We provide a default.
            "position": {"x": 0, "y": 0} 
        }
    
    def __repr__(self):
        return f"<{self.spec.get('display_name', self.node_type)} config={self.config.keys()}>"


class NodeCategory:
    """Helper to access nodes by category (client.nodes.source.S3Loader)."""
    def __init__(self, name: str):
        self._name = name
        self._node_classes = {}

    def _register(self, name: str, node_cls: type):
        self._node_classes[name] = node_cls
        # Also allow access as attribute if valid identifier
        if name.isidentifier():
            setattr(self, name, node_cls)
            
    def __getattr__(self, name: str):
        if name in self._node_classes:
            return self._node_classes[name]
        raise AttributeError(f"Category '{self._name}' has no node '{name}'")


class NodeFactory:
    """
    Dynamically creates Node classes based on the catalog.
    """
    def __init__(self, catalog: Any, mode: str = "rag"):
        self.catalog = catalog
        self.mode = mode
        self.categories = {}
        
        if mode == "rag":
            self._build_rag_factory()
        else:
            self._build_agent_factory()

    def _build_rag_factory(self):
        # Catalog is Dict[category, List[OperatorSpec]] or List[OperatorSpec]??
        # Checking registry.py: get_catalog returns Dict[category_name, List[spec]] usually?
        # Actually checking registry.py logic... it calls list_all then groups? 
        # Wait, get_catalog returns Dict[str, List[Dict]]
        
        # Let's handle both Dict (grouped) and List (flat) inputs to be safe
        all_specs = []
        if isinstance(self.catalog, dict):
            for cat, specs in self.catalog.items():
                if isinstance(specs, list):
                    all_specs.extend(specs)
        elif isinstance(self.catalog, list):
            all_specs = self.catalog
            
        for spec in all_specs:
            op_id = spec.get("operator_id")
            cat_name = spec.get("category", "custom")
            
            # Create a dynamic class for this node
            node_cls = self._create_node_class(op_id, spec)
            
            # Register in category helper
            if cat_name not in self.categories:
                self.categories[cat_name] = NodeCategory(cat_name)
            
            # CamelCase the class name helper (e.g. "s3_loader" -> "S3Loader")
            class_name = "".join(x.title() for x in op_id.split("_"))
            self.categories[cat_name]._register(class_name, node_cls)
            # Also register the raw ID for scripts
            self.categories[cat_name]._register(op_id, node_cls)
            
    def _build_agent_factory(self):
        # Agent catalog is typically a List[AgentOperatorSpec]
        for spec in self.catalog:
            op_type = spec.get("type")
            cat_name = spec.get("category", "general")
            
            node_cls = self._create_node_class(op_type, spec)
            
            if cat_name not in self.categories:
                self.categories[cat_name] = NodeCategory(cat_name)
                
            class_name = "".join(x.title() for x in op_type.split("_"))
            self.categories[cat_name]._register(class_name, node_cls)
            self.categories[cat_name]._register(op_type, node_cls)

    def _create_node_class(self, op_id: str, spec: Dict[str, Any]) -> type:
        """Create a class that initializes a Node with this specific spec."""
        def __init__(self, **kwargs):
            # Verify kwargs against spec['config_schema'] or 'required_config'
            # For now, minimal validation or just pass through
            Node.__init__(self, op_id, config=kwargs, spec=spec)
            
        return type(op_id, (Node,), {"__init__": __init__})

    def __getattr__(self, name: str):
        if name in self.categories:
            return self.categories[name]
        raise AttributeError(f"No node category '{name}'. Available: {list(self.categories.keys())}")
