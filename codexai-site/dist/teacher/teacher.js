'use strict';

const form = document.getElementById('login-form');
const message = document.getElementById('message');
const password = document.getElementById('password');
const submit = document.getElementById('login-button');
const toggle = document.getElementById('toggle-password');

async function existingSession() {
  const response = await fetch('/api/admin/session', {credentials: 'same-origin'});
  if (response.ok) window.location.replace('/teacher/dashboard/');
}

toggle.addEventListener('click', () => {
  const visible = password.type === 'text';
  password.type = visible ? 'password' : 'text';
  toggle.textContent = visible ? '显示' : '隐藏';
  toggle.setAttribute('aria-label', visible ? '显示密码' : '隐藏密码');
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  message.textContent = '';
  submit.disabled = true;
  submit.textContent = '正在登录…';
  try {
    const response = await fetch('/api/admin/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        username: document.getElementById('username').value.trim().toLowerCase(),
        password: password.value,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || '登录失败，请稍后重试');
    password.value = '';
    window.location.replace('/teacher/dashboard/');
  } catch (error) {
    message.textContent = error.message;
    password.select();
  } finally {
    submit.disabled = false;
    submit.textContent = '进入工作台';
  }
});

existingSession().catch(() => {});
