import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the placeholder scaffolding message', () => {
    render(<App />)

    expect(screen.getByText(/scaffolding in progress/i)).toBeInTheDocument()
  })
})
