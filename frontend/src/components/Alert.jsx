export default function Alert({ variant = 'error', children, style, className = '' }) {
  return (
    <div
      role={variant === 'error' ? 'alert' : 'status'}
      className={`alert alert-${variant}${className ? ` ${className}` : ''}`}
      style={style}
    >
      {children}
    </div>
  )
}
