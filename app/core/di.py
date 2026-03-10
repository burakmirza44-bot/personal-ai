"""Dependency Injection Module.

Provides a complete DI container with:
- Service lifetime management (singleton, transient, scoped)
- Dependency resolution
- Circular dependency detection
- Fluent registration API
- Service locator pattern

Usage:
    from app.core.di import ServiceBuilder, ServiceLocator

    # Create container
    builder = ServiceBuilder()
    (builder
        .add_singleton(IMemoryStore, implementation=MemoryStore)
        .add_transient(IPlanner, implementation=Planner)
    )
    container = builder.build()

    # Resolve services
    memory = container.resolve(IMemoryStore)

    # Or use service locator
    ServiceLocator.set_locator(ServiceLocator(container))
    memory = ServiceLocator.get_locator().get_service(IMemoryStore)
"""

from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar, get_type_hints

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ------------------------------------------------------------------
# Service Lifetime & Scope
# ------------------------------------------------------------------


class ServiceLifetime(Enum):
    """Service lifetime management."""

    SINGLETON = "singleton"  # One instance for entire application
    TRANSIENT = "transient"  # New instance each time
    SCOPED = "scoped"  # One instance per scope (e.g., per request)


class ServiceScope(Enum):
    """Service scopes for scoped lifetime."""

    APPLICATION = "application"  # Application-wide scope
    EXECUTION = "execution"  # Per execution scope
    REQUEST = "request"  # Per request scope


# ------------------------------------------------------------------
# Service Descriptor
# ------------------------------------------------------------------


@dataclass
class ServiceDescriptor(Generic[T]):
    """Describes a service to be registered.

    A service must have exactly one of:
    - implementation: A class to instantiate
    - factory: A callable that creates the instance
    - instance: A pre-created instance
    """

    service_type: Type[T]
    implementation: Optional[Type[T]] = None
    factory: Optional[Callable[..., T]] = None
    instance: Optional[T] = None
    lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT
    scope: ServiceScope = ServiceScope.APPLICATION
    tags: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validation: must have exactly one of implementation, factory, or instance
        implementations = sum(
            [
                self.implementation is not None,
                self.factory is not None,
                self.instance is not None,
            ]
        )

        if implementations != 1:
            raise ValueError(
                f"Service {self.service_type.__name__} must have exactly one of: "
                "implementation, factory, or instance"
            )

    def is_singleton(self) -> bool:
        """Check if service is singleton."""
        return self.lifetime == ServiceLifetime.SINGLETON

    def has_instance(self) -> bool:
        """Check if service has fixed instance."""
        return self.instance is not None

    def is_scoped(self) -> bool:
        """Check if service is scoped."""
        return self.lifetime == ServiceLifetime.SCOPED

    def is_transient(self) -> bool:
        """Check if service is transient."""
        return self.lifetime == ServiceLifetime.TRANSIENT


# ------------------------------------------------------------------
# Service Interfaces (Contracts)
# ------------------------------------------------------------------


class IMemoryStore(ABC):
    """Memory store service interface."""

    @abstractmethod
    def get_items(self) -> List[Dict[str, Any]]:
        """Get all stored items."""
        pass

    @abstractmethod
    def add_item(self, item: Dict[str, Any]) -> None:
        """Add an item to the store."""
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for items matching query."""
        pass


class IRAGIndex(ABC):
    """RAG index service interface."""

    @abstractmethod
    def retrieve(self, query: str, max_chunks: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant chunks for query."""
        pass

    @abstractmethod
    def index_document(self, doc: Dict[str, Any]) -> None:
        """Index a document."""
        pass


class IBridgeExecutor(ABC):
    """Bridge executor service interface."""

    @abstractmethod
    async def execute(self, recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a recipe."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check bridge health."""
        pass


class IPlanner(ABC):
    """Planner service interface."""

    @abstractmethod
    async def plan(self, goal: str, domain: str = "") -> Dict[str, Any]:
        """Create a plan for the goal."""
        pass

    @abstractmethod
    def decompose(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Decompose plan into steps."""
        pass


class IErrorLogger(ABC):
    """Error logger service interface."""

    @abstractmethod
    def log_error(
        self,
        error: Exception | str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an error."""
        pass

    @abstractmethod
    def get_errors(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent errors."""
        pass


class IBridgeHealthMonitor(ABC):
    """Bridge health monitor service interface."""

    @abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        """Check bridge health status."""
        pass

    @abstractmethod
    def get_last_status(self) -> Optional[Dict[str, Any]]:
        """Get last health check status."""
        pass


class IKnowledgeStore(ABC):
    """Knowledge store service interface."""

    @abstractmethod
    def get_recipe(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        """Get a recipe by ID."""
        pass

    @abstractmethod
    def search_knowledge(
        self,
        query: str,
        domain: str = "",
    ) -> List[Dict[str, Any]]:
        """Search knowledge base."""
        pass

    @abstractmethod
    def store_knowledge(self, knowledge: Dict[str, Any]) -> str:
        """Store knowledge and return ID."""
        pass


class ICheckpointManager(ABC):
    """Checkpoint manager service interface."""

    @abstractmethod
    def create_checkpoint(
        self,
        execution_id: str,
        state: Dict[str, Any],
    ) -> str:
        """Create a checkpoint."""
        pass

    @abstractmethod
    def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Load a checkpoint."""
        pass


class IProviderRouter(ABC):
    """Provider router service interface."""

    @abstractmethod
    def select_provider(
        self,
        requirements: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Select appropriate provider."""
        pass

    @abstractmethod
    def get_available_providers(self) -> List[str]:
        """Get list of available providers."""
        pass


# ------------------------------------------------------------------
# Service Registry
# ------------------------------------------------------------------


class ServiceRegistry:
    """Registry of services and their descriptors."""

    def __init__(self) -> None:
        self._services: Dict[Type, ServiceDescriptor] = {}
        self._implementation_map: Dict[Type, Type] = {}  # interface -> impl

    def register(
        self,
        service_type: Type[T],
        implementation: Optional[Type[T]] = None,
        factory: Optional[Callable[..., T]] = None,
        instance: Optional[T] = None,
        lifetime: ServiceLifetime = ServiceLifetime.TRANSIENT,
        scope: ServiceScope = ServiceScope.APPLICATION,
        tags: Optional[Dict[str, str]] = None,
    ) -> ServiceDescriptor:
        """Register a service.

        Args:
            service_type: The service interface/type
            implementation: Class to instantiate
            factory: Callable that creates instance
            instance: Pre-created instance
            lifetime: Service lifetime (singleton, transient, scoped)
            scope: Service scope
            tags: Optional tags for grouping

        Returns:
            ServiceDescriptor for the registered service
        """
        descriptor = ServiceDescriptor(
            service_type=service_type,
            implementation=implementation,
            factory=factory,
            instance=instance,
            lifetime=lifetime,
            scope=scope,
            tags=tags or {},
        )

        self._services[service_type] = descriptor

        if implementation:
            self._implementation_map[service_type] = implementation

        logger.debug(
            f"Registered service {service_type.__name__} "
            f"with lifetime={lifetime.value}"
        )

        return descriptor

    def get_descriptor(self, service_type: Type[T]) -> Optional[ServiceDescriptor]:
        """Get service descriptor."""
        return self._services.get(service_type)

    def is_registered(self, service_type: Type) -> bool:
        """Check if service is registered."""
        return service_type in self._services

    def get_all_descriptors(self) -> Dict[Type, ServiceDescriptor]:
        """Get all service descriptors."""
        return self._services.copy()

    def get_implementation(self, service_type: Type) -> Optional[Type]:
        """Get implementation class for service type."""
        return self._implementation_map.get(service_type)

    def unregister(self, service_type: Type) -> bool:
        """Unregister a service.

        Returns:
            True if service was unregistered
        """
        if service_type in self._services:
            del self._services[service_type]
            if service_type in self._implementation_map:
                del self._implementation_map[service_type]
            return True
        return False

    def clear(self) -> None:
        """Clear all registrations."""
        self._services.clear()
        self._implementation_map.clear()


# ------------------------------------------------------------------
# Dependency Container
# ------------------------------------------------------------------


class DependencyContainer:
    """Dependency injection container.

    Manages service registration, resolution, and lifecycle.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        self.registry = registry
        self._singletons: Dict[Type, Any] = {}
        self._scoped_instances: Dict[str, Dict[Type, Any]] = {}
        self._current_scope: Optional[str] = None
        self._resolution_stack: List[Type] = []  # For cycle detection

    def resolve(self, service_type: Type[T]) -> T:
        """Resolve service instance.

        Args:
            service_type: The type of service to resolve

        Returns:
            Instance of requested service type

        Raises:
            ValueError: If service not registered
            RuntimeError: If circular dependency detected
        """
        descriptor = self.registry.get_descriptor(service_type)

        if not descriptor:
            raise ValueError(f"Service {service_type.__name__} not registered")

        # Check for circular dependency
        if service_type in self._resolution_stack:
            cycle = self._resolution_stack + [service_type]
            raise RuntimeError(
                f"Circular dependency detected: {' -> '.join(t.__name__ for t in cycle)}"
            )

        # If instance already provided, return it
        if descriptor.has_instance():
            return descriptor.instance

        # Singleton: return cached instance
        if descriptor.is_singleton():
            if service_type not in self._singletons:
                self._singletons[service_type] = self._create_instance(descriptor)
            return self._singletons[service_type]

        # Scoped: return instance for current scope
        if descriptor.is_scoped():
            if not self._current_scope:
                raise RuntimeError(
                    f"No active scope for scoped service {service_type.__name__}"
                )

            scope_id = self._current_scope

            if scope_id not in self._scoped_instances:
                self._scoped_instances[scope_id] = {}

            if service_type not in self._scoped_instances[scope_id]:
                self._scoped_instances[scope_id][service_type] = self._create_instance(
                    descriptor
                )

            return self._scoped_instances[scope_id][service_type]

        # Transient: create new instance
        return self._create_instance(descriptor)

    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """Create new instance from descriptor."""
        self._resolution_stack.append(descriptor.service_type)

        try:
            # Factory method
            if descriptor.factory:
                return self._create_from_factory(descriptor)

            # Class constructor
            if descriptor.implementation:
                return self._create_from_implementation(descriptor)

            raise RuntimeError(
                f"Cannot create instance for {descriptor.service_type.__name__}"
            )
        finally:
            self._resolution_stack.pop()

    def _create_from_factory(self, descriptor: ServiceDescriptor) -> Any:
        """Create instance using factory."""
        factory = descriptor.factory
        kwargs = {}

        # Use get_type_hints to resolve string annotations (PEP 563)
        try:
            type_hints = get_type_hints(factory)
        except Exception:
            type_hints = {}

        sig = inspect.signature(factory)

        for param_name, param in sig.parameters.items():
            param_type = type_hints.get(param_name, param.annotation)

            if param_type != inspect.Parameter.empty and param_type is not inspect.Parameter.empty:
                if isinstance(param_type, type) and self.registry.is_registered(param_type):
                    kwargs[param_name] = self.resolve(param_type)
            elif param.default != inspect.Parameter.empty:
                # Use default value
                pass

        return factory(**kwargs)

    def _create_from_implementation(self, descriptor: ServiceDescriptor) -> Any:
        """Create instance from implementation class."""
        impl = descriptor.implementation
        kwargs = {}

        # Use get_type_hints to resolve string annotations (PEP 563)
        try:
            type_hints = get_type_hints(impl.__init__)
        except Exception:
            type_hints = {}

        sig = inspect.signature(impl.__init__)

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Get the resolved type from type_hints
            param_type = type_hints.get(param_name, param.annotation)

            if param_type != inspect.Parameter.empty and param_type is not inspect.Parameter.empty:
                # Check if this type is registered
                if isinstance(param_type, type) and self.registry.is_registered(param_type):
                    kwargs[param_name] = self.resolve(param_type)
                elif param.default != inspect.Parameter.empty:
                    # Use default value
                    pass
            elif param.default != inspect.Parameter.empty:
                # Use default value
                pass

        return impl(**kwargs)

    async def resolve_async(self, service_type: Type[T]) -> T:
        """Resolve service asynchronously.

        For services that require async initialization.
        """
        instance = self.resolve(service_type)

        # If instance has async init, call it
        if hasattr(instance, "__aenter__"):
            await instance.__aenter__()

        return instance

    def create_scope(self, scope_id: str) -> None:
        """Create new execution scope."""
        self._current_scope = scope_id
        if scope_id not in self._scoped_instances:
            self._scoped_instances[scope_id] = {}
        logger.debug(f"Created scope: {scope_id}")

    def dispose_scope(self, scope_id: str) -> None:
        """Dispose of scoped instances."""
        if scope_id in self._scoped_instances:
            # Call dispose on instances if they have it
            for instance in self._scoped_instances[scope_id].values():
                if hasattr(instance, "dispose"):
                    instance.dispose()
                elif hasattr(instance, "close"):
                    instance.close()

            del self._scoped_instances[scope_id]
            logger.debug(f"Disposed scope: {scope_id}")

        if self._current_scope == scope_id:
            self._current_scope = None

    def validate(self) -> List[str]:
        """Validate container configuration.

        Check for missing dependencies, circular references, etc.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        for service_type, descriptor in self.registry.get_all_descriptors().items():
            # Check for circular dependency
            cycle = self._detect_cycle(service_type, set())
            if cycle:
                errors.append(
                    f"Circular dependency: {' -> '.join(t.__name__ for t in cycle)}"
                )

            # Check for missing dependencies
            missing = self._check_missing_dependencies(descriptor)
            for dep in missing:
                errors.append(
                    f"Missing dependency: {service_type.__name__} requires "
                    f"{dep.__name__} which is not registered"
                )

        return errors

    def _detect_cycle(
        self, service_type: Type, visited: set, path: Optional[List[Type]] = None
    ) -> Optional[List[Type]]:
        """Detect circular dependencies."""
        if path is None:
            path = []

        if service_type in path:
            return path[path.index(service_type) :] + [service_type]

        if service_type in visited:
            return None

        visited.add(service_type)
        path = path + [service_type]

        descriptor = self.registry.get_descriptor(service_type)
        if not descriptor:
            return None

        dependencies = self._get_dependencies(descriptor)

        for dep in dependencies:
            cycle = self._detect_cycle(dep, visited, path)
            if cycle:
                return cycle

        return None

    def _get_dependencies(self, descriptor: ServiceDescriptor) -> List[Type]:
        """Get service dependencies."""
        dependencies = []

        if descriptor.implementation:
            try:
                type_hints = get_type_hints(descriptor.implementation.__init__)
            except Exception:
                type_hints = {}

            sig = inspect.signature(descriptor.implementation.__init__)
            for param_name, param in sig.parameters.items():
                if param_name != "self":
                    param_type = type_hints.get(param_name, param.annotation)
                    if isinstance(param_type, type) and self.registry.is_registered(param_type):
                        dependencies.append(param_type)

        elif descriptor.factory:
            try:
                type_hints = get_type_hints(descriptor.factory)
            except Exception:
                type_hints = {}

            sig = inspect.signature(descriptor.factory)
            for param_name, param in sig.parameters.items():
                param_type = type_hints.get(param_name, param.annotation)
                if isinstance(param_type, type) and self.registry.is_registered(param_type):
                    dependencies.append(param_type)

        return dependencies

    def _check_missing_dependencies(self, descriptor: ServiceDescriptor) -> List[Type]:
        """Check for missing dependencies."""
        missing = []

        if descriptor.implementation:
            try:
                type_hints = get_type_hints(descriptor.implementation.__init__)
            except Exception:
                type_hints = {}

            sig = inspect.signature(descriptor.implementation.__init__)
            for param_name, param in sig.parameters.items():
                if param_name != "self":
                    param_type = type_hints.get(param_name, param.annotation)
                    if (
                        isinstance(param_type, type)
                        and not self.registry.is_registered(param_type)
                        and param.default == inspect.Parameter.empty
                    ):
                        missing.append(param_type)

        elif descriptor.factory:
            try:
                type_hints = get_type_hints(descriptor.factory)
            except Exception:
                type_hints = {}

            sig = inspect.signature(descriptor.factory)
            for param_name, param in sig.parameters.items():
                param_type = type_hints.get(param_name, param.annotation)
                if (
                    isinstance(param_type, type)
                    and not self.registry.is_registered(param_type)
                    and param.default == inspect.Parameter.empty
                ):
                    missing.append(param_type)

        return missing

    def dispose(self) -> None:
        """Dispose all singleton instances."""
        for instance in self._singletons.values():
            if hasattr(instance, "dispose"):
                instance.dispose()
            elif hasattr(instance, "close"):
                instance.close()

        self._singletons.clear()

        for scope_id in list(self._scoped_instances.keys()):
            self.dispose_scope(scope_id)

        logger.debug("Container disposed")


# ------------------------------------------------------------------
# Service Builder (Fluent API)
# ------------------------------------------------------------------


class ServiceBuilder:
    """Fluent builder for registering services."""

    def __init__(self) -> None:
        self.registry = ServiceRegistry()

    def add_singleton(
        self,
        service_type: Type[T],
        implementation: Optional[Type[T]] = None,
        factory: Optional[Callable[..., T]] = None,
        instance: Optional[T] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> "ServiceBuilder":
        """Register singleton service."""
        self.registry.register(
            service_type,
            implementation=implementation,
            factory=factory,
            instance=instance,
            lifetime=ServiceLifetime.SINGLETON,
            tags=tags,
        )
        return self

    def add_transient(
        self,
        service_type: Type[T],
        implementation: Optional[Type[T]] = None,
        factory: Optional[Callable[..., T]] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> "ServiceBuilder":
        """Register transient service."""
        self.registry.register(
            service_type,
            implementation=implementation,
            factory=factory,
            lifetime=ServiceLifetime.TRANSIENT,
            tags=tags,
        )
        return self

    def add_scoped(
        self,
        service_type: Type[T],
        implementation: Optional[Type[T]] = None,
        factory: Optional[Callable[..., T]] = None,
        scope: ServiceScope = ServiceScope.EXECUTION,
        tags: Optional[Dict[str, str]] = None,
    ) -> "ServiceBuilder":
        """Register scoped service."""
        self.registry.register(
            service_type,
            implementation=implementation,
            factory=factory,
            lifetime=ServiceLifetime.SCOPED,
            scope=scope,
            tags=tags,
        )
        return self

    def add_instance(self, service_type: Type[T], instance: T) -> "ServiceBuilder":
        """Register an existing instance."""
        self.registry.register(
            service_type,
            instance=instance,
            lifetime=ServiceLifetime.SINGLETON,
        )
        return self

    def build(self) -> DependencyContainer:
        """Build and return container.

        Raises:
            ValueError: If validation fails
        """
        container = DependencyContainer(self.registry)

        # Validate
        errors = container.validate()

        if errors:
            raise ValueError(
                f"Container validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        logger.info(
            f"Built DI container with {len(self.registry.get_all_descriptors())} services"
        )

        return container


# ------------------------------------------------------------------
# Service Locator
# ------------------------------------------------------------------


class ServiceLocator:
    """Service locator pattern for global service access.

    Alternative to constructor injection. Use sparingly - prefer
    constructor injection when possible.
    """

    _instance: Optional["ServiceLocator"] = None

    def __init__(self, container: DependencyContainer) -> None:
        self.container = container

    @classmethod
    def set_locator(cls, locator: "ServiceLocator") -> None:
        """Set global service locator."""
        cls._instance = locator
        logger.debug("Service locator configured")

    @classmethod
    def get_locator(cls) -> "ServiceLocator":
        """Get global service locator.

        Raises:
            RuntimeError: If locator not configured
        """
        if not cls._instance:
            raise RuntimeError("Service locator not configured. Call set_locator() first.")
        return cls._instance

    @classmethod
    def is_configured(cls) -> bool:
        """Check if service locator is configured."""
        return cls._instance is not None

    @classmethod
    def clear(cls) -> None:
        """Clear the service locator."""
        if cls._instance:
            cls._instance.container.dispose()
        cls._instance = None

    def get_service(self, service_type: Type[T]) -> T:
        """Get service by type."""
        return self.container.resolve(service_type)

    def get_services_by_tag(self, tag: str) -> Dict[Type, Any]:
        """Get all services with a specific tag."""
        services = {}

        for service_type, descriptor in self.container.registry.get_all_descriptors().items():
            if tag in descriptor.tags:
                services[service_type] = self.container.resolve(service_type)

        return services

    def has_service(self, service_type: Type) -> bool:
        """Check if service is registered."""
        return self.container.registry.is_registered(service_type)


# ------------------------------------------------------------------
# Convenience Functions
# ------------------------------------------------------------------


def get_service(service_type: Type[T]) -> T:
    """Get a service from the global locator.

    Convenience function for ServiceLocator.get_locator().get_service().
    """
    return ServiceLocator.get_locator().get_service(service_type)


def get_memory_store() -> IMemoryStore:
    """Get memory store service."""
    return get_service(IMemoryStore)


def get_rag_index() -> IRAGIndex:
    """Get RAG index service."""
    return get_service(IRAGIndex)


def get_planner() -> IPlanner:
    """Get planner service."""
    return get_service(IPlanner)


def get_error_logger() -> IErrorLogger:
    """Get error logger service."""
    return get_service(IErrorLogger)


# ------------------------------------------------------------------
# Decorator for Injectable Services
# ------------------------------------------------------------------


def injectable(service_type: Optional[Type] = None):
    """Decorator to mark a class as injectable.

    Usage:
        @injectable
        class MyService:
            pass

        @injectable(IMyService)
        class MyServiceImpl(IMyService):
            pass
    """

    def decorator(cls):
        cls._injectable = True
        cls._service_type = service_type or cls
        return cls

    # Handle both @injectable and @injectable(Type)
    # If service_type is actually a class (used without parentheses)
    if service_type is not None and isinstance(service_type, type):
        cls = service_type
        cls._injectable = True
        cls._service_type = cls
        return cls

    return decorator


def is_injectable(cls: Type) -> bool:
    """Check if a class is marked as injectable."""
    return getattr(cls, "_injectable", False)