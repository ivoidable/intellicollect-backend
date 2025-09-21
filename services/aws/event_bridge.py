"""AWS EventBridge service for event-driven architecture"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import structlog

from services.aws.base import AWSServiceBase, aws_error_handler
from core.config import settings

logger = structlog.get_logger()


class EventBridgeService(AWSServiceBase):
    """Service for publishing and managing events via AWS EventBridge"""

    def __init__(self):
        super().__init__('events')
        self.event_bus_name = 'billing-events'  # Custom event bus for billing system

    @aws_error_handler
    async def publish_event(
        self,
        source: str,
        detail_type: str,
        detail: Dict[str, Any],
        resources: Optional[List[str]] = None
    ) -> bool:
        """Publish an event to EventBridge"""
        self.ensure_initialized()

        event = {
            'Source': f"billing.intelligence.{source}",
            'DetailType': detail_type,
            'Detail': json.dumps(detail),
            'EventBusName': self.event_bus_name,
            'Time': datetime.utcnow()
        }

        if resources:
            event['Resources'] = resources

        result = await self.execute_with_retry(
            'put_events',
            {
                'Entries': [event]
            }
        )

        if result['FailedEntryCount'] > 0:
            logger.error(
                "Failed to publish event",
                source=source,
                detail_type=detail_type,
                failures=result['Entries']
            )
            return False

        logger.info(
            "Event published",
            source=source,
            detail_type=detail_type,
            event_id=result['Entries'][0].get('EventId')
        )
        return True

    @aws_error_handler
    async def publish_batch_events(
        self,
        events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Publish multiple events in a batch"""
        self.ensure_initialized()

        entries = []
        for event in events:
            entry = {
                'Source': f"billing.intelligence.{event['source']}",
                'DetailType': event['detail_type'],
                'Detail': json.dumps(event['detail']),
                'EventBusName': self.event_bus_name,
                'Time': datetime.utcnow()
            }
            if 'resources' in event:
                entry['Resources'] = event['resources']
            entries.append(entry)

        # EventBridge allows max 10 entries per request
        results = []
        for i in range(0, len(entries), 10):
            batch = entries[i:i+10]
            result = await self.execute_with_retry(
                'put_events',
                {'Entries': batch}
            )
            results.append(result)

        total_failed = sum(r['FailedEntryCount'] for r in results)
        total_sent = len(events) - total_failed

        logger.info(
            "Batch events published",
            total=len(events),
            successful=total_sent,
            failed=total_failed
        )

        return {
            'total': len(events),
            'successful': total_sent,
            'failed': total_failed,
            'results': results
        }

    # Business event publishers
    async def publish_invoice_created(
        self,
        invoice_id: str,
        customer_id: str,
        amount: float,
        due_date: str
    ):
        """Publish invoice created event"""
        return await self.publish_event(
            source='invoice',
            detail_type='InvoiceCreated',
            detail={
                'invoice_id': invoice_id,
                'customer_id': customer_id,
                'amount': amount,
                'due_date': due_date,
                'timestamp': datetime.utcnow().isoformat()
            },
            resources=[f"arn:aws:invoice:{invoice_id}"]
        )

    async def publish_payment_received(
        self,
        payment_id: str,
        invoice_id: str,
        customer_id: str,
        amount: float
    ):
        """Publish payment received event"""
        return await self.publish_event(
            source='payment',
            detail_type='PaymentReceived',
            detail={
                'payment_id': payment_id,
                'invoice_id': invoice_id,
                'customer_id': customer_id,
                'amount': amount,
                'timestamp': datetime.utcnow().isoformat()
            },
            resources=[f"arn:aws:payment:{payment_id}"]
        )

    async def publish_risk_assessment_completed(
        self,
        customer_id: str,
        risk_level: str,
        risk_score: float,
        factors: List[str]
    ):
        """Publish risk assessment completed event"""
        return await self.publish_event(
            source='risk',
            detail_type='RiskAssessmentCompleted',
            detail={
                'customer_id': customer_id,
                'risk_level': risk_level,
                'risk_score': risk_score,
                'factors': factors,
                'timestamp': datetime.utcnow().isoformat()
            }
        )

    async def publish_communication_sent(
        self,
        communication_id: str,
        customer_id: str,
        invoice_id: Optional[str],
        channel: str,
        type: str
    ):
        """Publish communication sent event"""
        return await self.publish_event(
            source='communication',
            detail_type='CommunicationSent',
            detail={
                'communication_id': communication_id,
                'customer_id': customer_id,
                'invoice_id': invoice_id,
                'channel': channel,
                'type': type,
                'timestamp': datetime.utcnow().isoformat()
            }
        )

    async def publish_customer_updated(
        self,
        customer_id: str,
        changed_fields: List[str]
    ):
        """Publish customer updated event"""
        return await self.publish_event(
            source='customer',
            detail_type='CustomerUpdated',
            detail={
                'customer_id': customer_id,
                'changed_fields': changed_fields,
                'timestamp': datetime.utcnow().isoformat()
            }
        )

    @aws_error_handler
    async def create_rule(
        self,
        rule_name: str,
        event_pattern: Dict[str, Any],
        description: Optional[str] = None,
        state: str = 'ENABLED'
    ):
        """Create an EventBridge rule"""
        self.ensure_initialized()

        params = {
            'Name': rule_name,
            'EventPattern': json.dumps(event_pattern),
            'State': state,
            'EventBusName': self.event_bus_name
        }

        if description:
            params['Description'] = description

        result = await self.execute_with_retry('put_rule', params)
        logger.info(f"EventBridge rule created", rule_name=rule_name)
        return result

    @aws_error_handler
    async def add_target(
        self,
        rule_name: str,
        target_arn: str,
        target_id: str
    ):
        """Add a target to an EventBridge rule"""
        self.ensure_initialized()

        result = await self.execute_with_retry(
            'put_targets',
            {
                'Rule': rule_name,
                'EventBusName': self.event_bus_name,
                'Targets': [
                    {
                        'Id': target_id,
                        'Arn': target_arn
                    }
                ]
            }
        )
        logger.info(
            "Target added to rule",
            rule_name=rule_name,
            target_id=target_id
        )
        return result