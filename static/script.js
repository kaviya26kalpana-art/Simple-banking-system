// Minimal client-side enhancements
document.addEventListener('submit', e => {
  const form = e.target;
  if(form.action && (form.action.endsWith('/deposit') || form.action.endsWith('/withdraw') || form.action.endsWith('/transfer'))){
    const amt = form.querySelector('input[name="amount"]');
    if(amt){
      const v = parseFloat(amt.value);
      if(isNaN(v) || v <= 0){
        alert('Please enter a positive amount');
        e.preventDefault();
      }
    }
  }
});