"""Customer Repository for DynamoDB operations"""

from typing import List, Optional, Dict, Any
from boto3.dynamodb.conditions import Key, Attr
import structlog

from app.dynamodb.client import dynamodb_client
from app.dynamodb.tables import TableNames, EntityTypes, GSINames, create_key_structure, create_gsi_keys
from app.dynamodb.models import Customer
from app.core.exceptions import DatabaseError

logger = structlog.get_logger()


class CustomerRepository:
    """Repository for customer-related database operations"""

    def __init__(self):
        self.db = dynamodb_client
        self.table_name = TableNames.MAIN

    async def create(self, customer: Customer) -> Customer:
        """Create a new customer"""
        try:
            # Prepare item for DynamoDB
            item = customer.dict_for_dynamodb()

            # Set primary keys
            keys = create_key_structure(EntityTypes.CUSTOMER, customer.id)
            item.update(keys)

            # Add GSI keys for querying
            item = create_gsi_keys(item, EntityTypes.CUSTOMER)

            # Add entity type for filtering
            item['EntityType'] = EntityTypes.CUSTOMER

            # Save to database
            await self.db.put_item(self.table_name, item)

            logger.info("Customer created", customer_id=customer.id, company_id=customer.company_id)
            return customer

        except Exception as e:
            logger.error(f"Failed to create customer", error=str(e))
            raise DatabaseError(f"Failed to create customer: {str(e)}")

    async def get_by_id(self, customer_id: str) -> Optional[Customer]:
        """Get a customer by ID"""
        try:
            pk = f"{EntityTypes.CUSTOMER}#{customer_id}"
            sk = "METADATA"

            item = await self.db.get_item(self.table_name, pk, sk)

            if not item:
                return None

            return Customer(**item)

        except Exception as e:
            logger.error(f"Failed to get customer", customer_id=customer_id, error=str(e))
            raise DatabaseError(f"Failed to get customer: {str(e)}")

    async def get_by_company(
        self,
        company_id: str,
        limit: int = 50,
        last_evaluated_key: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get all customers for a company"""
        try:
            # Use GSI5 for company queries
            key_condition = Key('GSI5PK').eq(f"COMPANY#{company_id}") & Key('GSI5SK').begins_with('CUSTOMER#')

            result = await self.db.query(
                self.table_name,
                key_condition=key_condition,
                index_name=GSINames.GSI5,
                limit=limit,
                last_evaluated_key=last_evaluated_key
            )

            customers = [Customer(**item) for item in result['Items']]

            return {
                'customers': customers,
                'count': result['Count'],
                'last_evaluated_key': result.get('LastEvaluatedKey')
            }

        except Exception as e:
            logger.error(f"Failed to get customers by company", company_id=company_id, error=str(e))
            raise DatabaseError(f"Failed to get customers: {str(e)}")

    async def get_by_email(self, company_id: str, email: str) -> Optional[Customer]:
        """Get customer by email within a company"""
        try:
            # Query customers by company
            key_condition = Key('GSI5PK').eq(f"COMPANY#{company_id}") & Key('GSI5SK').begins_with('CUSTOMER#')
            filter_expression = Attr('email').eq(email.lower())

            result = await self.db.query(
                self.table_name,
                key_condition=key_condition,
                index_name=GSINames.GSI5,
                filter_expression=filter_expression,
                limit=1
            )

            if result['Items']:
                return Customer(**result['Items'][0])

            return None

        except Exception as e:
            logger.error(f"Failed to get customer by email", email=email, error=str(e))
            raise DatabaseError(f"Failed to get customer by email: {str(e)}")

    async def update(self, customer_id: str, updates: Dict[str, Any]) -> Customer:
        """Update a customer"""
        try:
            pk = f"{EntityTypes.CUSTOMER}#{customer_id}"
            sk = "METADATA"

            # If company_id is being updated, update GSI keys
            if 'company_id' in updates:
                item = await self.db.get_item(self.table_name, pk, sk)
                if item:
                    item.update(updates)
                    item = create_gsi_keys(item, EntityTypes.CUSTOMER)
                    await self.db.put_item(self.table_name, item)
                    return Customer(**item)
            else:
                # Simple update without changing GSI keys
                updated_item = await self.db.update_item(
                    self.table_name,
                    pk,
                    sk,
                    updates
                )
                return Customer(**updated_item)

        except Exception as e:
            logger.error(f"Failed to update customer", customer_id=customer_id, error=str(e))
            raise DatabaseError(f"Failed to update customer: {str(e)}")

    async def delete(self, customer_id: str) -> bool:
        """Delete a customer (soft delete)"""
        try:
            # Soft delete by updating is_active flag
            updates = {'is_active': False}
            await self.update(customer_id, updates)

            logger.info("Customer deleted", customer_id=customer_id)
            return True

        except Exception as e:
            logger.error(f"Failed to delete customer", customer_id=customer_id, error=str(e))
            raise DatabaseError(f"Failed to delete customer: {str(e)}")

    async def search(
        self,
        company_id: str,
        search_term: str,
        limit: int = 50
    ) -> List[Customer]:
        """Search customers by name or email"""
        try:
            # Query all customers for the company
            key_condition = Key('GSI5PK').eq(f"COMPANY#{company_id}") & Key('GSI5SK').begins_with('CUSTOMER#')

            # Filter by search term
            filter_expression = (
                Attr('customer_name').contains(search_term) |
                Attr('email').contains(search_term.lower()) |
                Attr('customer_company').contains(search_term)
            )

            result = await self.db.query(
                self.table_name,
                key_condition=key_condition,
                index_name=GSINames.GSI5,
                filter_expression=filter_expression,
                limit=limit
            )

            return [Customer(**item) for item in result['Items']]

        except Exception as e:
            logger.error(f"Failed to search customers", search_term=search_term, error=str(e))
            raise DatabaseError(f"Failed to search customers: {str(e)}")

    async def get_active_count(self, company_id: str) -> int:
        """Get count of active customers for a company"""
        try:
            # Query active customers
            key_condition = Key('GSI5PK').eq(f"COMPANY#{company_id}") & Key('GSI5SK').begins_with('CUSTOMER#')
            filter_expression = Attr('is_active').eq(True)

            result = await self.db.query(
                self.table_name,
                key_condition=key_condition,
                index_name=GSINames.GSI5,
                filter_expression=filter_expression
            )

            return result['Count']

        except Exception as e:
            logger.error(f"Failed to get active customer count", company_id=company_id, error=str(e))
            raise DatabaseError(f"Failed to get customer count: {str(e)}")