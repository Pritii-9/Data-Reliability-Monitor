from src.db.database import SessionLocal, Ticket
from src.services.alerting import send_alert
from datetime import datetime
import os

def create_ticket(title, description, severity="LOW"):
    """
    Creates a new incident ticket in the database and triggers an email alert.
    """
    session = SessionLocal()
    try:
        new_ticket = Ticket(
            title=title,
            description=description,
            severity=severity,
            status="OPEN"
        )
        session.add(new_ticket)
        session.commit()
        session.refresh(new_ticket)
        
        # Trigger alert only if it's a manual run
        if os.getenv("MANUAL_RUN") == "true":
            send_alert(title, description, severity, new_ticket.created_at)
        else:
            print("Skipping email alert (background run).")
        
        return new_ticket
    except Exception as e:
        session.rollback()
        print(f"Error creating ticket: {e}")
        return None
    finally:
        session.close()

def resolve_ticket(ticket_id):
    """
    Marks a ticket as resolved.
    """
    session = SessionLocal()
    try:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket:
            ticket.status = "RESOLVED"
            ticket.resolved_at = datetime.utcnow()
            session.commit()
            print(f"Ticket {ticket_id} resolved.")
            return True
        print(f"Ticket {ticket_id} not found.")
        return False
    except Exception as e:
        session.rollback()
        print(f"Error resolving ticket: {e}")
        return False
    finally:
        session.close()

def resolve_all_tickets():
    """
    Marks all currently open tickets as resolved in bulk.
    """
    session = SessionLocal()
    try:
        session.query(Ticket).filter(Ticket.status == "OPEN").update(
            {Ticket.status: "RESOLVED", Ticket.resolved_at: datetime.utcnow()},
            synchronize_session=False
        )
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"Error resolving all tickets: {e}")
        return False
    finally:
        session.close()
