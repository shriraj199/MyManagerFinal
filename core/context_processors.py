from core.models import PaymentProof

def pending_reviews(request):
    if not request.user.is_authenticated:
        return {}
        
    if request.user.role == 'secretary':
        count = PaymentProof.objects.filter(
            society_name=request.user.society_name,
            status__in=['pending', 'flagged']
        ).count()
        return {'pending_reviews_count': count}
    
    elif request.user.role == 'resident' and request.user.resident_role == 'owner':
        # Owners might want to see if their tenant uploaded a proof?
        # But usually, it's the secretary who reviews.
        pass
        
    return {'pending_reviews_count': 0}
