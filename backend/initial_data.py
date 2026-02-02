from sqlalchemy.orm import Session
from . import models

DEFAULT_GROUPS = [
    {
        "name": "Income",
        "sort_order": 0,
        "categories": [
            {"name": "Paycheck", "type": "income", "sort_order": 0},
            {"name": "Bonus", "type": "income", "sort_order": 1},
            {"name": "Interest", "type": "income", "sort_order": 2},
        ]
    },
    {
        "name": "Saving",
        "sort_order": 0,
        "categories": [
            {"name": "House Fund", "type": "expense", "sort_order": 0}
        ]
    },
    {
        "name": "Housing",
        "sort_order": 1,
        "categories": [
            {"name": "Rent/Mortgage", "type": "expense", "sort_order": 0},
            {"name": "Utilities", "type": "expense", "sort_order": 1},
            {"name": "Maintenance", "type": "expense", "sort_order": 2},
        ]
    },
    {
        "name": "Food",
        "sort_order": 2,
        "categories": [
            {"name": "Groceries", "type": "expense", "sort_order": 0},
            {"name": "Restaurants", "type": "expense", "sort_order": 1},
        ]
    },
    {
        "name": "Transportation",
        "sort_order": 3,
        "categories": [
            {"name": "Fuel", "type": "expense", "sort_order": 0},
            {"name": "Public Transit", "type": "expense", "sort_order": 1},
            {"name": "Service/Parts", "type": "expense", "sort_order": 2},
        ]
    }
]

def init_db(db: Session):
    """
    Initialize the database with default category groups and categories if they don't exist.
    """
    for group_data in DEFAULT_GROUPS:
        # Check if group exists
        group = db.query(models.CategoryGroup).filter_by(name=group_data["name"]).first()
        
        if not group:
            group = models.CategoryGroup(
                name=group_data["name"],
                sort_order=group_data["sort_order"]
            )
            db.add(group)
            db.commit()
            db.refresh(group)
            print(f"Created Group: {group.name}")
        
        # Check and create categories
        for cat_data in group_data["categories"]:
            category = db.query(models.Category).filter_by(
                name=cat_data["name"],
                group_id=group.category_group_id
            ).first()
            
            if not category:
                category = models.Category(
                    name=cat_data["name"],
                    group_id=group.category_group_id,
                    type=cat_data["type"],
                    sort_order=cat_data["sort_order"]
                )
                db.add(category)
                db.commit()
                print(f"  Created Category: {category.name} ({category.type})")
