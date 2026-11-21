/**
 * authForm unit tests: email validation + the §7.8 error mapping
 * (status → exact plan message key, never raw backend detail).
 */
import { describe, expect, it } from 'vitest'
import { ApiError } from './auth'
import { classifyAuthError, isValidEmail } from './authForm'

describe('isValidEmail', () => {
  it('accepts ordinary addresses', () => {
    expect(isValidEmail('user@example.com')).toBe(true)
    expect(isValidEmail('a.b+tag@sub.example.co.uk')).toBe(true)
  })

  it('rejects malformed addresses', () => {
    expect(isValidEmail('not-an-email')).toBe(false)
    expect(isValidEmail('user@')).toBe(false)
    expect(isValidEmail('@example.com')).toBe(false)
    expect(isValidEmail('user name@example.com')).toBe(false)
    expect(isValidEmail('')).toBe(false)
  })
})

describe('classifyAuthError', () => {
  it('401 → invalid credentials banner', () => {
    expect(classifyAuthError(new ApiError(401, 'Invalid email or password'), 'login')).toEqual({
      banner: 'err.invalidCredentials',
    })
  })

  it('409 → email already registered banner', () => {
    expect(classifyAuthError(new ApiError(409, 'Email already registered'), 'register')).toEqual({
      banner: 'err.emailTaken',
    })
  })

  it('429 on login → the lock message (backend cannot distinguish the two 429 cases)', () => {
    expect(classifyAuthError(new ApiError(429, 'Too many requests'), 'login')).toEqual({
      banner: 'err.locked',
    })
  })

  it('429 on register → the rate-limit message', () => {
    expect(classifyAuthError(new ApiError(429, 'Too many requests'), 'register')).toEqual({
      banner: 'err.tooFrequent',
    })
  })

  it('422 → field error on the email field', () => {
    expect(classifyAuthError(new ApiError(422, 'Unprocessable'), 'register')).toEqual({
      field: 'err.invalidEmail',
    })
  })

  it('500 / 503 → server banner', () => {
    expect(classifyAuthError(new ApiError(500, 'boom'), 'login')).toEqual({
      banner: 'err.server',
    })
    expect(classifyAuthError(new ApiError(503, 'down'), 'login')).toEqual({
      banner: 'err.server',
    })
  })

  it('a thrown non-ApiError (e.g. fetch TypeError) → network banner', () => {
    expect(classifyAuthError(new TypeError('Failed to fetch'), 'login')).toEqual({
      banner: 'err.network',
    })
  })
})
