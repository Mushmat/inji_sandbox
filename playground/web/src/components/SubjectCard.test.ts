import { describe, expect, it } from 'vitest'
import { problemWith } from './SubjectCard'

// Same rules as playground/bff/identity.py; the backend tests cover that side.
describe('credential subject validation', () => {
  it('wants a 9-digit Farmer ID', () => {
    expect(problemWith('farmerID', '123748599')).toBeNull()
    expect(problemWith('farmerID', '12345')).not.toBeNull()
  })
  it('wants an Indian mobile number and PIN code', () => {
    expect(problemWith('mobileNumber', '9998882226')).toBeNull()
    expect(problemWith('mobileNumber', '1234567890')).not.toBeNull()
    expect(problemWith('postalCode', '012345')).not.toBeNull()
  })
  it('wants a real date of birth in the past', () => {
    expect(problemWith('dateOfBirth', '11-11-1999')).toBeNull()
    expect(problemWith('dateOfBirth', '31-02-2000')).not.toBeNull()
    expect(problemWith('dateOfBirth', '01-01-2999')).not.toBeNull()
  })
  it("doesn't check the photo here", () => {
    expect(problemWith('face', '')).toBeNull()
  })
})
