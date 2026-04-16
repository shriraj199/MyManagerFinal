from core.models import PaymentProof

def pending_reviews(request):
    if not request.user.is_authenticated:
        return {}
        
    from .models import User
    
    context = {'pending_reviews_count': 0, 'society_secretary': None}
    
    if request.user.role == 'secretary':
        from .models import PaymentProof
        count = PaymentProof.objects.filter(
            society_name=request.user.society_name,
            status__in=['pending', 'flagged']
        ).count()
        context['pending_reviews_count'] = count
    
    # Always try to find the secretary for the user's society
    secretary = User.objects.filter(society_name=request.user.society_name, role='secretary').first()
    context['society_secretary'] = secretary
        
    return context
