// static/js/course_price.js
document.addEventListener('DOMContentLoaded', function () {
    const priceTypeSelect = document.querySelector('#id_price_type');
    const partnerPriceInput = document.querySelector('#id_partner_price');
    const discountPercentInput = document.querySelector('#id_discount_percent');

    function togglePriceFields() {
        if (!priceTypeSelect || !partnerPriceInput || !discountPercentInput) return;

        // Ambil opsi yang dipilih
        const selectedOption = priceTypeSelect.options[priceTypeSelect.selectedIndex];
        // Cek apakah opsi memiliki data-free='true'
        const isFree = selectedOption && selectedOption.dataset.free === 'true';

        partnerPriceInput.disabled = isFree;
        discountPercentInput.disabled = isFree;

        if (isFree) {
            partnerPriceInput.value = '0';
            discountPercentInput.value = '0';
        }
    }

    if (priceTypeSelect) {
        priceTypeSelect.addEventListener('change', togglePriceFields);
        togglePriceFields();
    }
});