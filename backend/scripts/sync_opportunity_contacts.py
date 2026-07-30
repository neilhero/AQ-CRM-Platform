from app.database import SessionLocal
from app.models import Opportunity
from app.routers.opportunities import _sync_opportunity_contacts


def main():
    db = SessionLocal()
    try:
        opportunities = (
            db.query(Opportunity)
            .filter(Opportunity.customer_id.isnot(None))
            .all()
        )
        for opportunity in opportunities:
            _sync_opportunity_contacts(db, opportunity)
        db.commit()
        print(f"Synced contacts from {len(opportunities)} opportunities")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
