"""AWS Risk Assessment service integration"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import structlog

from app.services.aws.base import AWSServiceBase, aws_error_handler
from app.core.config import settings
from app.services.cache import CacheService

logger = structlog.get_logger()


class RiskAssessmentService(AWSServiceBase):
    """Service for AI-powered risk assessment using AWS Lambda and SageMaker"""

    def __init__(self):
        super().__init__('lambda')
        self.function_name = settings.AWS_LAMBDA_RISK_ASSESSMENT_FUNCTION
        self.cache = CacheService()

    @aws_error_handler
    async def assess_customer_risk(
        self,
        customer_id: str,
        payment_history: Optional[List[Dict]] = None,
        invoice_history: Optional[List[Dict]] = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Assess customer credit risk using AI"""
        self.ensure_initialized()

        # Check cache first
        if not force_refresh:
            cache_key = f"risk:customer:{customer_id}"
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.info("Using cached risk assessment", customer_id=customer_id)
                return json.loads(cached_result)

        # Prepare payload for Lambda
        payload = {
            'customer_id': customer_id,
            'assessment_type': 'customer',
            'payment_history': payment_history or [],
            'invoice_history': invoice_history or [],
            'timestamp': datetime.utcnow().isoformat()
        }

        # Invoke Lambda function
        result = await self.execute_with_retry(
            'invoke',
            {
                'FunctionName': self.function_name,
                'InvocationType': 'RequestResponse',
                'Payload': json.dumps(payload)
            }
        )

        # Parse response
        response_payload = json.loads(result['Payload'].read())

        if result['StatusCode'] != 200:
            logger.error(
                "Risk assessment failed",
                customer_id=customer_id,
                error=response_payload.get('error')
            )
            raise Exception(f"Risk assessment failed: {response_payload.get('error')}")

        risk_assessment = response_payload.get('risk_assessment', {})

        # Cache result
        cache_key = f"risk:customer:{customer_id}"
        await self.cache.set(
            cache_key,
            json.dumps(risk_assessment),
            expire=3600  # 1 hour cache
        )

        logger.info(
            "Customer risk assessed",
            customer_id=customer_id,
            risk_level=risk_assessment.get('risk_level'),
            risk_score=risk_assessment.get('risk_score')
        )

        return risk_assessment

    @aws_error_handler
    async def assess_invoice_risk(
        self,
        invoice_id: str,
        customer_id: str,
        amount: float,
        due_date: str,
        line_items: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Assess invoice payment risk"""
        self.ensure_initialized()

        # Check cache
        cache_key = f"risk:invoice:{invoice_id}"
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.info("Using cached invoice risk assessment", invoice_id=invoice_id)
            return json.loads(cached_result)

        # Prepare payload
        payload = {
            'invoice_id': invoice_id,
            'customer_id': customer_id,
            'assessment_type': 'invoice',
            'amount': amount,
            'due_date': due_date,
            'line_items': line_items or [],
            'timestamp': datetime.utcnow().isoformat()
        }

        # Invoke Lambda
        result = await self.execute_with_retry(
            'invoke',
            {
                'FunctionName': self.function_name,
                'InvocationType': 'RequestResponse',
                'Payload': json.dumps(payload)
            }
        )

        # Parse response
        response_payload = json.loads(result['Payload'].read())

        if result['StatusCode'] != 200:
            logger.error(
                "Invoice risk assessment failed",
                invoice_id=invoice_id,
                error=response_payload.get('error')
            )
            raise Exception(f"Invoice risk assessment failed")

        risk_assessment = response_payload.get('risk_assessment', {})

        # Cache result
        await self.cache.set(
            cache_key,
            json.dumps(risk_assessment),
            expire=3600
        )

        logger.info(
            "Invoice risk assessed",
            invoice_id=invoice_id,
            payment_probability=risk_assessment.get('payment_probability'),
            estimated_payment_date=risk_assessment.get('estimated_payment_date')
        )

        return risk_assessment

    @aws_error_handler
    async def get_collection_strategy(
        self,
        customer_id: str,
        invoice_id: str,
        days_overdue: int,
        risk_level: str
    ) -> Dict[str, Any]:
        """Get AI-recommended collection strategy"""
        self.ensure_initialized()

        payload = {
            'customer_id': customer_id,
            'invoice_id': invoice_id,
            'assessment_type': 'collection_strategy',
            'days_overdue': days_overdue,
            'risk_level': risk_level,
            'timestamp': datetime.utcnow().isoformat()
        }

        result = await self.execute_with_retry(
            'invoke',
            {
                'FunctionName': self.function_name,
                'InvocationType': 'RequestResponse',
                'Payload': json.dumps(payload)
            }
        )

        response_payload = json.loads(result['Payload'].read())

        if result['StatusCode'] != 200:
            logger.error(
                "Collection strategy generation failed",
                invoice_id=invoice_id,
                error=response_payload.get('error')
            )
            raise Exception(f"Collection strategy generation failed")

        strategy = response_payload.get('collection_strategy', {})

        logger.info(
            "Collection strategy generated",
            invoice_id=invoice_id,
            strategy_type=strategy.get('strategy_type'),
            urgency=strategy.get('urgency')
        )

        return strategy

    @aws_error_handler
    async def batch_assess_risks(
        self,
        assessments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Perform batch risk assessments"""
        self.ensure_initialized()

        results = []
        for assessment in assessments:
            try:
                if assessment['type'] == 'customer':
                    result = await self.assess_customer_risk(
                        customer_id=assessment['customer_id'],
                        payment_history=assessment.get('payment_history'),
                        invoice_history=assessment.get('invoice_history')
                    )
                elif assessment['type'] == 'invoice':
                    result = await self.assess_invoice_risk(
                        invoice_id=assessment['invoice_id'],
                        customer_id=assessment['customer_id'],
                        amount=assessment['amount'],
                        due_date=assessment['due_date']
                    )
                else:
                    result = {'error': f"Unknown assessment type: {assessment['type']}"}

                results.append({
                    'id': assessment.get('id'),
                    'type': assessment['type'],
                    'result': result,
                    'status': 'success'
                })
            except Exception as e:
                results.append({
                    'id': assessment.get('id'),
                    'type': assessment['type'],
                    'error': str(e),
                    'status': 'failed'
                })

        successful = len([r for r in results if r['status'] == 'success'])
        logger.info(
            "Batch risk assessment completed",
            total=len(assessments),
            successful=successful,
            failed=len(assessments) - successful
        )

        return results

    def calculate_local_risk_score(
        self,
        days_overdue: int,
        payment_history: List[Dict],
        invoice_amount: float,
        customer_age_days: int
    ) -> Dict[str, Any]:
        """Calculate risk score locally as fallback"""
        # Simple heuristic-based risk scoring
        risk_score = 0.5  # Base score

        # Factor in days overdue
        if days_overdue > 90:
            risk_score += 0.3
        elif days_overdue > 60:
            risk_score += 0.2
        elif days_overdue > 30:
            risk_score += 0.1

        # Factor in payment history
        if payment_history:
            late_payments = len([p for p in payment_history if p.get('late', False)])
            late_ratio = late_payments / len(payment_history)
            risk_score += late_ratio * 0.2

        # Factor in invoice amount (higher amounts = higher risk)
        if invoice_amount > 10000:
            risk_score += 0.1
        elif invoice_amount > 5000:
            risk_score += 0.05

        # Factor in customer age (newer customers = higher risk)
        if customer_age_days < 30:
            risk_score += 0.15
        elif customer_age_days < 90:
            risk_score += 0.05

        # Normalize score between 0 and 1
        risk_score = min(max(risk_score, 0), 1)

        # Determine risk level
        if risk_score >= 0.7:
            risk_level = 'critical'
        elif risk_score >= 0.5:
            risk_level = 'high'
        elif risk_score >= 0.3:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        return {
            'risk_score': risk_score,
            'risk_level': risk_level,
            'calculation_method': 'local_heuristic',
            'factors': {
                'days_overdue': days_overdue,
                'payment_history_score': len(payment_history),
                'invoice_amount': invoice_amount,
                'customer_age_days': customer_age_days
            }
        }