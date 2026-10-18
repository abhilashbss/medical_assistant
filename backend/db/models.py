from sqlalchemy import Column, Integer, String, ForeignKey, Table, Boolean, Index
from sqlalchemy.orm import relationship, declarative_base
from geoalchemy2 import Geometry
from sqlalchemy import text

Base = declarative_base()

# Junction table for many-to-many relationship between Providers and NetworkPlans
provider_networks = Table(
    'provider_networks',
    Base.metadata,
    Column('provider_id', Integer, ForeignKey('providers.id'), primary_key=True),
    Column('plan_id', Integer, ForeignKey('insurance_plans.id'), primary_key=True),
    Column('is_in_network', Boolean, default=True, nullable=False),
    Column('network_tier', String(50)), # e.g., 'Tier 1', 'Preferred'
)

class InsuranceCarrier(Base):
    __tablename__ = 'insurance_carriers'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    payer_id = Column(String(100), nullable=False, unique=True)

    plans = relationship("NetworkPlan", back_populates="carrier")

class NetworkPlan(Base):
    __tablename__ = 'insurance_plans'

    id = Column(Integer, primary_key=True)
    carrier_id = Column(Integer, ForeignKey('insurance_carriers.id'), nullable=False)
    plan_name = Column(String(255), nullable=False)
    plan_type = Column(String(100)) # e.g., 'PPO', 'HMO', 'EPO'
    tier = Column(String(50)) # e.g., 'Gold', 'Silver'

    carrier = relationship("InsuranceCarrier", back_populates="plans")
    providers = relationship("Provider", secondary=provider_networks, back_populates="plans")

class Provider(Base):
    __tablename__ = 'providers'

    id = Column(Integer, primary_key=True)
    npi = Column(String(10), nullable=False, unique=True) # National Provider Identifier
    name = Column(String(255), nullable=False)
    specialty = Column(String(255), nullable=False)

    # HIPAA Compliance: PHI/PII are handled via PHIColumn or separate secure storage.
    # For the core provider identity, these are usually considered public/professional data.
    # However, specific contact details might be treated as sensitive.
    address = Column(String(500))

    # Geospatial location (Point: longitude, latitude)
    # SRID 4326 is the standard for GPS coordinates (WGS 84)
    location = Column(Geometry('POINT', srid=4326), nullable=False)

    plans = relationship("NetworkPlan", secondary=provider_networks, back_populates="providers")

    # Geospatial index for radius searches
    __table_args__ = (
        Index('ix_provider_location', 'location', postgresql_using='gist'),
    )

class PHIColumn:
    """
    A descriptor or wrapper to mark columns that contain PHI.
    In a real implementation, this would integrate with the encryption layer
    to automatically encrypt/decrypt during SQLAlchemy load/save.
    """
    def __init__(self, column_name):
        self.column_name = column_name
