//untuk menu static
const toggleBtn = document.getElementById('navbarToggle');
        const closeBtn = document.getElementById('closeMenu');
        const mobileMenu = document.getElementById('navbarNavMobile');
        const overlay = document.getElementById('overlay');

        toggleBtn.addEventListener('click', () => {
            mobileMenu.classList.add('active');
            overlay.classList.add('active');
        });

        closeBtn.addEventListener('click', () => {
            mobileMenu.classList.remove('active');
            overlay.classList.remove('active');
        });

        overlay.addEventListener('click', () => {
            mobileMenu.classList.remove('active');
            overlay.classList.remove('active');
        });
//popular courses
document.addEventListener('DOMContentLoaded', function () {
  const coursesList = document.getElementById('courses-list');
  if (!coursesList) return;

  fetch('/popular_courses/')
    .then(response => response.json())
    .then(data => {
      coursesList.innerHTML = ''; // clear existing content

      data.courses.forEach(course => {
        const courseUrl = `/course-detail/${course.id}/${encodeURIComponent(course.slug)}/`;
        const instructorPhoto = course.instructor_photo || '/static/images/user-default.webp';
        const org_logo = course.org_logo || '/static/images/user-default.webp';

        const isFree = (course.user_payment === 0);

        // Use rating stars from backend directly
        const ratingStars = [
          ...Array(course.full_stars).fill(`<svg class="h-4 w-4 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 15l-5.878 3.09L5.49 12.18 1 7.91l6.061-.545L10 2.5l2.939 4.865 6.061.545-4.49 4.27 1.368 5.91z"/>
          </svg>`),
          course.half_star ? `<svg class="h-4 w-4 text-yellow-400" viewBox="0 0 20 20">
            <defs>
              <linearGradient id="half-${course.id}">
                <stop offset="50%" stop-color="currentColor"/>
                <stop offset="50%" stop-color="transparent"/>
              </linearGradient>
            </defs>
            <path fill="url(#half-${course.id})" d="M10 15l-5.878 3.09L5.49 12.18 1 7.91l6.061-.545L10 2.5l2.939 4.865 6.061.545-4.49 4.27 1.368 5.91z"/>
          </svg>` : '',
          ...Array(course.empty_stars).fill(`<svg class="h-4 w-4 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 15l-5.878 3.09L5.49 12.18 1 7.91l6.061-.545L10 2.5l2.939 4.865 6.061.545-4.49 4.27 1.368 5.91z"/>
          </svg>`)
        ].join('');

        const courseHtml = `
          
            <article 
              class="group bg-white rounded-2xl shadow-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-0.5 focus-within:shadow-xl focus-within:-translate-y-0.5 overflow-hidden flex flex-col h-full"
              itemscope 
              itemtype="https://schema.org/Course"
            >
              <a 
                href="${courseUrl}" 
                title="Lihat kursus: ${course.course_name || 'Untitled Course'}" 
                class="block flex-grow flex flex-col focus:outline-none"
                itemprop="url"
                aria-label="Detail kursus ${course.course_name || 'tanpa judul'}"
              >

                <!-- 1. Thumbnail -->
                <div class="relative overflow-hidden">
                  <img 
                    src="${course.image || '/static/images/placeholder-300.webp'}"
                    srcset="
                      ${course.image || '/static/images/placeholder-150.webp'} 150w,
                      ${course.image || '/static/images/placeholder-300.webp'} 300w,
                      ${course.image || '/static/images/placeholder-600.webp'} 600w"
                    sizes="(max-width: 640px) 100vw, 300px"
                    alt="${course.course_name || 'Gambar kursus'}"
                    class="w-full h-full object-cover transition-transform duration-300 hover:scale-105"
                    loading="lazy"
                    decoding="async"
                    itemprop="image"
                  >
                </div>

                <!-- Body -->
                <div class="p-4 sm:p-5 flex flex-col flex-grow">

                  <!-- 2. Title -->
                  <h3 
                    class="text-base sm:text-lg font-semibold text-gray-900 line-clamp-2 mb-2 group-hover:text-emerald-700 transition-colors"
                    itemprop="name"
                  >
                    ${course.course_name || 'Untitled Course'}
                  </h3>

                  <!-- 3. Category | Level | Language -->
                  <p class="text-xs sm:text-sm text-gray-600 mb-3 truncate">
                    ${course.category || 'Kategori'} | ${course.level || 'Level'} | ${course.language ? course.language.charAt(0).toUpperCase() + course.language.slice(1) : 'Bahasa'}
                  </p>

                  <!-- 4. Price / Free + Rating & Enrollments -->
                  <div class="flex items-center justify-between mb-4 text-sm">

                    <!-- Price / Free -->
                    <div>
                      ${isFree 
                        ? `<span class="bg-green-700 text-white text-xs font-semibold px-2 py-1 rounded-md shadow">FREE</span>`
                        : `<span class=" bg-blue-700 text-white text-xs font-semibold px-2 py-1 rounded-md shadow">
                            IDR ${typeof course.user_payment === 'number' ? course.user_payment.toLocaleString('id-ID') : 'N/A'}
                          </span>`
                      }
                    </div>

                    <!-- Rating & Enrollments -->
                    <div class="flex items-center gap-4">
                      <!-- Rating -->
                      <div class="flex items-center">
                        <div class="${course.num_ratings === 0 ? 'text-gray-300' : 'text-amber-400'} flex items-center gap-0.5">
                          ${ratingStars || '<span class="text-gray-400">—</span>'}
                        </div>
                        <span class="ml-1.5 text-gray-500">(${course.num_ratings || 0})</span>
                      </div>

                      <!-- Enrollments -->
                      <div class="flex items-center gap-1.5 text-gray-600">
                        <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/>
                        </svg>
                        <span>${course.num_enrollments?.toLocaleString('id-ID') || 0}</span>
                      </div>
                    </div>
                  </div>

                  <!-- 5. Footer: Instructor & Partner -->
                  <div class="mt-auto flex items-center pt-3 border-t border-gray-100">
                    <img 
                      src="${org_logo || '/static/images/placeholder-org.webp'}" 
                      alt="${course.org_name || 'Partner'}" 
                      class="w-6 h-6 rounded-full mr-3 object-cover border border-gray-200"
                      loading="lazy"
                      itemprop="provider" itemscope itemtype="https://schema.org/Organization"
                    >
                    <div class="flex flex-col text-xs sm:text-sm leading-tight truncate flex-1">
                      <p class="text-gray-700 font-semibold truncate" itemprop="name">
                        ${course.org_name || 'Unknown Partner'}
                      </p>
                      <p class="text-gray-500 truncate">
                        ${course.instructor_name || 'N/A'}
                      </p>
                    </div>
                  </div>

                </div>
              </a>
            </article>
          `;

        coursesList.insertAdjacentHTML('beforeend', courseHtml);
      });
    })
    .catch(err => {
      coursesList.innerHTML = '<p class="text-red-600">Failed to load courses. Please try again later.</p>';
      console.error(err);
    });
});


//untuk course detail

 document.addEventListener("DOMContentLoaded", function() {
        if (typeof Fancybox !== 'undefined') {
            Fancybox.bind('[data-fancybox="video-gallery"]', {
                infinite: false,
                arrows: true,
                closeButton: "top",
                dragToClose: true
            });
        } else {
            console.warn('Fancybox is not loaded. Video lightbox functionality will not work.');
        }
    });

    function openShareWindow() {
        const courseUrl = window.location.href;
        const encodedUrl = encodeURIComponent(courseUrl);
        const shareUrls = {
            facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`,
            twitter: `https://twitter.com/intent/tweet?url=${encodedUrl}&text=Check out this course!`,
            whatsapp: `https://api.whatsapp.com/send?text=Check out this course: ${encodedUrl}`
        };
        const platform = 'facebook';
        const windowOptions = `height=400,width=600,top=${(window.innerHeight / 2 - 200)},left=${(window.innerWidth / 2 - 300)}`;
        if (shareUrls[platform]) {
            window.open(shareUrls[platform], '_blank', windowOptions);
        } else {
            console.error('Platform not supported');
        }
    }

    function toggleReplyForm(formId) {
        const form = document.getElementById(formId);
        form.classList.toggle('hidden');
    }


    //script untuk micro detail
        document.addEventListener("DOMContentLoaded", function() {
        if (typeof Fancybox !== 'undefined') {
            Fancybox.bind('[data-fancybox="video-gallery"]', {
                infinite: false,
                arrows: true,
                closeButton: "top",
                dragToClose: true
            });
        } else {
            console.warn('Fancybox is not loaded. Video lightbox functionality will not work.');
        }
    });

    function openShareWindow() {
        var courseUrl = window.location.href;
        var encodedUrl = encodeURIComponent(courseUrl);
        var shareUrls = {
            facebook: 'https://www.facebook.com/sharer/sharer.php?u=' + encodedUrl,
            twitter: 'https://twitter.com/intent/tweet?url=' + encodedUrl + '&text=Check out this microcredential!',
            whatsapp: 'https://api.whatsapp.com/send?text=Check out this microcredential: ' + encodedUrl
        };
        var platform = 'facebook';
        var windowOptions = 'height=400,width=600,top=' + (window.innerHeight / 2 - 200) + ',left=' + (window.innerWidth / 2 - 300);
        if (shareUrls[platform]) {
            window.open(shareUrls[platform], '_blank', windowOptions);
        } else {
            console.error('Platform not supported');
        }
    }


    //script post detail
    function showReplyForm(commentId) {
    // Hide all reply forms
    document.querySelectorAll('.reply-form').forEach(form => form.classList.add('hidden'));
    // Show the target reply form
    const targetForm = document.getElementById(`reply-form-${commentId}`);
    if (targetForm) {
        targetForm.classList.remove('hidden');
    }
    }


 






  