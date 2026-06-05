# Reference Files

This document lists reference files and patterns to follow (or avoid) in the project.

---

## Golden References (Follow These)

### Endpoint Pattern

**File:** `/app/api/endpoints/bookings.py` *(TODO: Create as reference)*

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db_session
from app.services.booking_service import BookingService
from app.schemas.booking import BookingResponse, BookingCreate

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

def get_booking_service(db: AsyncSession = Depends(get_db_session)) -> BookingService:
    """Dependency injector for BookingService."""
    from app.db.repositories.booking_repository import BookingRepository
    repo = BookingRepository(db)
    return BookingService(repo)

@router.get("/", response_model=list[BookingResponse])
async def list_bookings(
    service: BookingService = Depends(get_booking_service)
) -> list[BookingResponse]:
    """List all bookings."""
    bookings = await service.list_all()
    return [BookingResponse.model_validate(b) for b in bookings]

@router.post("/", response_model=BookingResponse, status_code=201)
async def create_booking(
    data: BookingCreate,
    service: BookingService = Depends(get_booking_service)
) -> BookingResponse:
    """Create a new booking."""
    booking = await service.create_booking(data)
    return BookingResponse.model_validate(booking)
```

**Why it's good:**
- ✅ Dependency injection pattern
- ✅ Service layer abstraction
- ✅ Pydantic schemas for validation
- ✅ Proper response models
- ✅ Type annotations throughout

---

### Service Pattern

**File:** `/app/services/booking_service.py` *(TODO: Create as reference)*

```python
from app.db.repositories.booking_repository import BookingRepository
from app.schemas.booking import BookingCreate
from app.db.models.booking import Booking
from app.exceptions import SlotNotAvailableError, BookingNotFoundError

class BookingService:
    """Business logic for booking operations."""
    
    def __init__(self, repository: BookingRepository):
        self.repository = repository
    
    async def create_booking(self, data: BookingCreate) -> Booking:
        """
        Create a new booking.
        
        Args:
            data: Booking creation data
            
        Returns:
            Created booking
            
        Raises:
            SlotNotAvailableError: If slot is already booked
        """
        # Check availability first
        is_available = await self.repository.is_slot_available(data.slot_start)
        if not is_available:
            raise SlotNotAvailableError(data.slot_start)
        
        # Create booking
        return await self.repository.create(data)
    
    async def get_by_id(self, booking_id: int) -> Booking:
        """
        Get booking by ID.
        
        Raises:
            BookingNotFoundError: If booking doesn't exist
        """
        booking = await self.repository.get_by_id(booking_id)
        if booking is None:
            raise BookingNotFoundError(booking_id)
        return booking
```

**Why it's good:**
- ✅ Single responsibility
- ✅ Clear error handling
- ✅ Docstrings with raises
- ✅ Type hints complete
- ✅ No direct DB access

---

### Repository Pattern

**File:** `/app/db/repositories/booking_repository.py` *(TODO: Create as reference)*

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.booking import Booking
from app.schemas.booking import BookingCreate
from typing import Optional

class BookingRepository:
    """Data access layer for bookings."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, booking_id: int) -> Optional[Booking]:
        """Get booking by ID."""
        result = await self.session.execute(
            select(Booking).where(Booking.id == booking_id)
        )
        return result.scalar_one_or_none()
    
    async def create(self, data: BookingCreate) -> Booking:
        """Create new booking."""
        booking = Booking(**data.model_dump())
        self.session.add(booking)
        await self.session.commit()
        await self.session.refresh(booking)
        return booking
    
    async def is_slot_available(self, slot_start: datetime) -> bool:
        """Check if time slot is available."""
        result = await self.session.execute(
            select(Booking)
            .where(Booking.slot_start == slot_start)
            .where(Booking.status != 'cancelled')
        )
        return result.scalar_one_or_none() is None
```

**Why it's good:**
- ✅ Session encapsulation
- ✅ SQLAlchemy ORM usage
- ✅ Type hints
- ✅ Clear method names

---

### Pydantic Schema Pattern

**File:** `/app/schemas/booking.py` *(TODO: Create as reference)*

```python
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from enum import Enum

class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class BookingCreate(BaseModel):
    """Schema for creating a booking."""
    slot_start: datetime
    customer_name: str = Field(min_length=2, max_length=255)
    customer_email: EmailStr

class BookingResponse(BaseModel):
    """Schema for booking response."""
    id: int
    slot_start: datetime
    customer_name: str
    customer_email: str
    status: BookingStatus
    created_at: datetime
    
    class Config:
        from_attributes = True
```

**Why it's good:**
- ✅ Enum for status values
- ✅ EmailStr validation
- ✅ Field constraints
- ✅ Separate create/response schemas
- ✅ ORM mode enabled

---

### Test Pattern

**File:** `/tests/services/test_booking_service.py` *(TODO: Create as reference)*

```python
import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from app.services.booking_service import BookingService
from app.exceptions import SlotNotAvailableError

@pytest.fixture
def mock_repository():
    repo = AsyncMock()
    repo.is_slot_available = AsyncMock(return_value=True)
    repo.create = AsyncMock()
    return repo

@pytest.fixture
def booking_service(mock_repository):
    return BookingService(mock_repository)

class TestBookingServiceCreate:
    """Tests for BookingService.create_booking."""
    
    async def test_create_booking_success(self, booking_service, mock_repository):
        """Test successful booking creation."""
        # Arrange
        data = BookingCreate(
            slot_start=datetime(2025, 1, 15, 10, 0),
            customer_name="John Doe",
            customer_email="john@example.com"
        )
        
        # Act
        result = await booking_service.create_booking(data)
        
        # Assert
        assert result is not None
        mock_repository.is_slot_available.assert_called_once()
        mock_repository.create.assert_called_once()
    
    async def test_create_booking_slot_taken(self, booking_service, mock_repository):
        """Test booking creation when slot is taken."""
        # Arrange
        mock_repository.is_slot_available.return_value = False
        data = BookingCreate(...)
        
        # Act & Assert
        with pytest.raises(SlotNotAvailableError):
            await booking_service.create_booking(data)
```

**Why it's good:**
- ✅ AAA pattern (Arrange-Act-Assert)
- ✅ Fixtures for reuse
- ✅ Test isolation
- ✅ Error case coverage
- ✅ Descriptive test names

---

## Anti-References (Do NOT Follow)

### Legacy Code Markers

Look for these comments indicating code to avoid copying:

```python
# LEGACY: Do not use as example
# TODO: Refactor this endpoint
# DEPRECATED: Use new /api/v2/ endpoints
# HACK: Temporary workaround for issue #123
```

### Common Anti-Patterns

```python
# ❌ BAD: Direct DB access in endpoint
@router.get("/bookings")
async def get_bookings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Booking))
    return result.scalars().all()

# ❌ BAD: No type hints
async def create_booking(data):
    ...

# ❌ BAD: Business logic in endpoint
@router.post("/bookings")
async def create(data, db):
    if "@" not in data.email:  # Validation in wrong place
        raise HTTPException(400)
    ...

# ❌ BAD: Parallel types
class BookingDTO(BaseModel): ...
class BookingSchema(BaseModel): ...  # Duplicate!
class BookingModel(BaseModel): ...   # Which one to use?
```

---

## TODO: Files to Create as References

The following reference files should be created:

| File | Purpose | Priority |
|------|---------|----------|
| `/app/api/endpoints/bookings.py` | Endpoint pattern | High |
| `/app/services/booking_service.py` | Service pattern | High |
| `/app/db/repositories/booking_repository.py` | Repository pattern | High |
| `/app/schemas/booking.py` | Schema pattern | High |
| `/tests/services/test_booking_service.py` | Test pattern | High |
| `/tests/api/test_bookings.py` | API test pattern | Medium |
| `/app/exceptions.py` | Exception pattern | Medium |
| `/app/db/models/booking.py` | Model pattern | High |

---

## Reference Updates

When adding new patterns:

1. Create the implementation
2. Add to this document as golden reference
3. Document why it's a good pattern
4. Update skills to reference new file

When refactoring legacy:

1. Mark old code with `# LEGACY` comment
2. Create new reference implementation
3. Update this document
4. Migrate callers incrementally
