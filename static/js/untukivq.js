// static/js/in-video-quiz.js
// FINAL VERSION - In-video quiz styled like QUIZIZZ (clean & soft colors, no gradient)
// Features: DB restore, auto-show on timeupdate, prevent double submit
// UI/UX: Solid soft colors (indigo, green, red), subtle glow, smooth animations

const quizState = {
    quizzes: [],
    score: 0,
    answeredQuizzes: {},  // { 0: {answered: true, correct: true, userAnswer: "A", shown: true/false} }
    currentQuizIndex: 0,
    video: null,
    overlay: null,
    quizCard: null,
    questionText: null,
    optionsContainer: null,
    nextButton: null,
    explanation: null,
    scoreDisplay: null,
    progressText: null
};

function getCSRFToken() {
    const name = "csrftoken=";
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.startsWith(name)) return cookie.substring(name.length);
    }
    return null;
}

function playSound(correct) {
    const sound = correct ? document.getElementById('correctSound') : document.getElementById('wrongSound');
    if (sound) {
        sound.pause();
        sound.currentTime = 0;
        sound.volume = 0.7;
        sound.play().catch(() => {});
    }
}

function updateScoreDisplay() {
    const answeredCount = Object.keys(quizState.answeredQuizzes).length;
    if (quizState.scoreDisplay) {
        quizState.scoreDisplay.textContent = `${quizState.score} / ${answeredCount}`;
    }
}

function continueWatching() {
    if (quizState.video && quizState.video.paused) {
        quizState.video.play();
    }
    quizState.overlay.classList.remove('active');
}

function endQuiz() {
    const videoEl = quizState.video;
    const assessmentId = videoEl.dataset.assessment;

    quizState.overlay.classList.add('active');

    quizState.nextButton.disabled = true;
    quizState.nextButton.innerHTML = '<span class="animate-spin inline-block mr-2">⟳</span> Saving...';

    fetch(`/video/${videoEl.dataset.id}/save-result/${assessmentId}/`, {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify({
            score: quizState.score,
            total: quizState.quizzes.length,
            answers: quizState.answeredQuizzes
        })
    })
    .then(res => res.ok ? res.json() : res.text().then(text => { throw new Error(text) }))
    .then(data => {
        console.log("Saved:", data);
        // QUIZIZZ-style final screen with soft colors
        quizState.quizCard.innerHTML = `
            <div class="text-center py-12 px-6 bg-white rounded-3xl shadow-2xl">
                <i class="fas fa-trophy text-9xl text-yellow-400 mb-8 animate-bounce"></i>
                <h2 class="text-5xl font-extrabold mb-6 text-indigo-800">Quiz Completed!</h2>
                <p class="text-7xl font-black text-green-600 mb-10">${quizState.score}/${quizState.quizzes.length}</p>
                <button onclick="continueWatching()" class="w-full bg-green-500 hover:bg-green-600 text-white font-bold py-6 rounded-2xl text-2xl transition transform hover:scale-105 shadow-xl">
                    Continue Watching
                </button>
            </div>`;
    })
    .catch(err => {
        console.error("Save failed:", err);
        alert('Failed to save quiz result. Please try again or continue watching.');
        quizState.nextButton.disabled = false;
        quizState.nextButton.innerHTML = 'Next →';
    });
}

function showQuiz(index) {
    const q = quizState.quizzes[index];
    quizState.video.pause();
    quizState.overlay.classList.add('active');
    gsap.to(quizState.quizCard, {scale: 1, opacity: 1, duration: 0.7, ease: "back.out(1.7)"});

    if (quizState.progressText) {
        quizState.progressText.textContent = `Question ${index + 1} of ${quizState.quizzes.length}`;
    }

    quizState.questionText.textContent = q.question;
    quizState.optionsContainer.innerHTML = '';
    quizState.explanation.classList.add('hidden');
    quizState.nextButton.classList.add('hidden');

    const alreadyAnswered = quizState.answeredQuizzes[index];

    if (alreadyAnswered && alreadyAnswered.answered) {
        renderAnsweredView(q, index, alreadyAnswered);
        quizState.explanation.textContent = q.explanation || "";
        quizState.explanation.classList.remove('hidden');
        gsap.fromTo(quizState.explanation, {opacity: 0, y: 30}, {opacity: 1, y: 0, duration: 0.6, delay: 0.4});
        quizState.nextButton.classList.remove('hidden');
        return;
    }

    renderFreshQuiz(q, index);
}

function renderAnsweredView(q, index, answeredData) {
    if (q.type === "multiple-choice") {
        q.options.forEach((opt, i) => {
            const btn = document.createElement('button');
            btn.className = "w-full p-6 text-center rounded-2xl font-bold text-lg disabled:opacity-80 transition-all min-h-[64px] shadow-md";
            btn.textContent = opt;
            btn.disabled = true;

            if (i === q.correct) {
                btn.classList.add("bg-green-500", "text-white", "ring-4", "ring-green-300");
            }
            if (i === answeredData.userAnswer && !answeredData.correct) {
                btn.classList.add("bg-red-500", "text-white", "ring-4", "ring-red-300");
            }
            if (i !== q.correct && i !== answeredData.userAnswer) {
                btn.classList.add("bg-indigo-100", "text-indigo-900");
            }

            quizState.optionsContainer.appendChild(btn);
        });
    } else if (q.type === "true-false") {
        ["False", "True"].forEach(label => {
            const btn = document.createElement('button');
            btn.className = "w-full p-7 text-2xl font-extrabold rounded-2xl text-white mb-5 min-h-[70px] transition-all shadow-lg";
            btn.textContent = label;
            btn.disabled = true;

            const isCorrectLabel = label === "True";
            if (isCorrectLabel) {
                btn.classList.add("bg-green-500", "ring-4", "ring-green-300");
            }
            if (answeredData.userAnswer === label && !answeredData.correct) {
                btn.classList.add("bg-red-500", "ring-4", "ring-red-300");
            }

            quizState.optionsContainer.appendChild(btn);
        });
    } else if (q.type === "fill-blank" || q.type === "es") {
        const input = document.createElement('input');
        input.type = "text";
        input.value = answeredData.userAnswer || "";
        input.disabled = true;
        input.className = "w-full p-6 text-2xl text-center border-4 rounded-2xl outline-none min-h-[64px] " +
                         (answeredData.correct 
                            ? "bg-green-500 text-white border-green-300 ring-4 ring-green-200" 
                            : "bg-red-500 text-white border-red-300 ring-4 ring-red-200");
        quizState.optionsContainer.appendChild(input);
    } else if (q.type === "drag-and-drop") {
        const drop = document.createElement('div');
        drop.className = "border-4 border-dashed border-indigo-400 rounded-2xl h-40 mb-6 flex items-center justify-center text-xl font-bold bg-indigo-50 shadow-inner";
        drop.textContent = answeredData.userAnswer || "Answer: " + q.correct;
        quizState.optionsContainer.appendChild(drop);
    }
}

function renderFreshQuiz(q, index) {
    const handleAnswer = (correct, element, userAnswer) => {
        const answered = quizState.answeredQuizzes[index];
        if (answered && answered.answered) return;

        quizState.answeredQuizzes[index] = {
            answered: true,
            correct: correct,
            userAnswer: userAnswer !== undefined ? userAnswer : (element?.value || element?.textContent || element?.dataset?.value) || null,
            shown: true
        };

        if (correct) quizState.score++;
        playSound(correct);

        if (element) {
            if (correct) {
                element.classList.add("bg-green-500", "text-white", "ring-4", "ring-green-300", "scale-105", "transition-all", "duration-300");
            } else {
                element.classList.add("bg-red-500", "text-white", "ring-4", "ring-red-300", "scale-105", "transition-all", "duration-300");
            }
        }
        quizState.optionsContainer.querySelectorAll("button, input").forEach(btn => btn.disabled = true);

        quizState.explanation.textContent = q.explanation || "";
        quizState.explanation.classList.remove('hidden');
        gsap.fromTo(quizState.explanation, {opacity: 0, y: 30}, {opacity: 1, y: 0, duration: 0.6, delay: 0.4});
        quizState.nextButton.classList.remove('hidden');

        updateScoreDisplay();
    };

    if (q.type === "multiple-choice") {
        q.options.forEach((opt, i) => {
            const btn = document.createElement('button');
            btn.className = "w-full p-6 text-center bg-indigo-500 hover:bg-indigo-600 text-white rounded-2xl font-bold text-lg transition transform hover:scale-105 min-h-[64px] shadow-lg focus:outline-none focus:ring-4 focus:ring-indigo-300";
            btn.textContent = opt;
            btn.onclick = () => handleAnswer(i === q.correct, btn, i);
            quizState.optionsContainer.appendChild(btn);
        });
    } else if (q.type === "true-false") {
        const correctIsTrue = q.correct === true ||
                             String(q.correct).toLowerCase() === "true" ||
                             String(q.correct).toLowerCase() === "correct" ||
                             String(q.correct).toLowerCase() === "benar";

        const falseBtn = document.createElement('button');
        falseBtn.className = "w-full p-7 text-2xl font-extrabold rounded-2xl bg-red-500 hover:bg-red-600 text-white mb-5 min-h-[70px] transition transform hover:scale-105 shadow-lg focus:outline-none focus:ring-4 focus:ring-red-300";
        falseBtn.textContent = "False";
        falseBtn.onclick = () => handleAnswer(!correctIsTrue, falseBtn, "False");

        const trueBtn = document.createElement('button');
        trueBtn.className = "w-full p-7 text-2xl font-extrabold rounded-2xl bg-green-500 hover:bg-green-600 text-white min-h-[70px] transition transform hover:scale-105 shadow-lg focus:outline-none focus:ring-4 focus:ring-green-300";
        trueBtn.textContent = "True";
        trueBtn.onclick = () => handleAnswer(correctIsTrue, trueBtn, "True");

        quizState.optionsContainer.appendChild(falseBtn);
        quizState.optionsContainer.appendChild(trueBtn);
    } else if (q.type === "fill-blank" || q.type === "es") {
        const input = document.createElement('input');
        input.type = "text";
        input.autofocus = true;
        input.placeholder = "Type your answer here...";
        input.className = "w-full p-6 text-2xl text-center border-4 border-indigo-400 rounded-2xl focus:border-indigo-600 focus:ring-4 focus:ring-indigo-300 outline-none min-h-[64px] shadow-md";

        const submit = document.createElement('button');
        submit.textContent = "Submit";
        submit.className = "mt-6 w-full bg-indigo-500 hover:bg-indigo-600 text-white font-bold py-5 rounded-2xl text-xl transition transform hover:scale-105 min-h-[64px] shadow-lg";
        submit.onclick = () => handleAnswer(input.value.trim().toLowerCase() === String(q.correct).toLowerCase(), input, input.value.trim());

        input.addEventListener('keydown', e => e.key === 'Enter' && submit.click());
        quizState.optionsContainer.appendChild(input);
        quizState.optionsContainer.appendChild(submit);
    } else if (q.type === "drag-and-drop") {
        const dropZone = document.createElement('div');
        dropZone.className = "border-4 border-dashed border-indigo-400 rounded-2xl h-40 mb-6 flex items-center justify-center text-xl font-bold bg-indigo-50 transition";
        dropZone.textContent = "Drop your answer here";
        dropZone.ondragover = e => e.preventDefault();
        dropZone.ondrop = e => {
            e.preventDefault();
            const text = e.dataTransfer.getData("text");
            handleAnswer(text === q.correct, dropZone, text);
            dropZone.textContent = text;
            dropZone.classList.add("bg-indigo-200", "border-indigo-600");
        };
        quizState.optionsContainer.appendChild(dropZone);

        const items = document.createElement('div');
        items.className = "grid grid-cols-2 gap-5";
        q.items.forEach(item => {
            const el = document.createElement('div');
            el.className = "bg-indigo-500 text-white p-6 rounded-2xl text-center cursor-move select-none text-lg font-bold min-h-[64px] shadow-lg transition transform hover:scale-105";
            el.textContent = item;
            el.draggable = true;
            el.ondragstart = e => e.dataTransfer.setData("text", item);
            items.appendChild(el);
        });
        quizState.optionsContainer.appendChild(items);
    }
}

function setupNextButton() {
    if (quizState.nextButton) {
        quizState.nextButton.innerHTML = 'Next →';
        quizState.nextButton.className = "mt-8 w-full bg-indigo-500 hover:bg-indigo-600 text-white font-bold py-5 rounded-2xl text-xl transition transform hover:scale-105 min-h-[64px] shadow-xl";
        quizState.nextButton.onclick = () => {
            quizState.overlay.classList.remove('active');
            quizState.currentQuizIndex++;
            if (quizState.currentQuizIndex < quizState.quizzes.length) {
                quizState.video.play();
            } else {
                endQuiz();
            }
        };
    }
}

function handleTimeUpdate() {
    quizState.quizzes.forEach((q, index) => {
        const answered = quizState.answeredQuizzes[index];
        if (quizState.video.currentTime >= q.time && (!answered || !answered.shown)) {
            if (!answered) {
                quizState.answeredQuizzes[index] = { shown: true };
            } else {
                answered.shown = true;
            }
            showQuiz(index);
        }
    });
}

function initVideoQuiz() {
    const video = document.getElementById('myVideo');
    if (!video) return;

    quizState.video = video;
    quizState.overlay = document.getElementById('quizOverlay');
    quizState.quizCard = document.querySelector('.quiz-card');
    quizState.questionText = document.getElementById('questionText');
    quizState.optionsContainer = document.getElementById('optionsContainer');
    quizState.nextButton = document.getElementById('nextButton');
    quizState.explanation = document.getElementById('explanation');
    quizState.scoreDisplay = document.getElementById('scoreDisplay');
    quizState.progressText = document.getElementById('progressText');

    quizState.quizzes = JSON.parse(video.dataset.quizzes || '[]');
    const resultJson = video.dataset.resultJson || 'null';
    const result = resultJson !== 'null' ? JSON.parse(resultJson) : null;

    quizState.score = 0;
    quizState.answeredQuizzes = {};
    quizState.currentQuizIndex = 0;

    if (result) {
        quizState.score = result.score || 0;
        if (result.answers) {
            quizState.answeredQuizzes = {};
            Object.entries(result.answers).forEach(([key, saved]) => {
                quizState.answeredQuizzes[key] = {
                    answered: true,
                    correct: saved.correct || false,
                    userAnswer: saved.userAnswer !== undefined ? saved.userAnswer : null,
                    shown: true
                };
            });
        }
    }

    updateScoreDisplay();
    setupNextButton();

    video.removeEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('timeupdate', handleTimeUpdate);
}

document.body.addEventListener('htmx:afterSwap', (evt) => {
    if (evt.detail.target.id === 'content-area') {
        setTimeout(initVideoQuiz, 100);
    }
});

document.addEventListener('DOMContentLoaded', initVideoQuiz);