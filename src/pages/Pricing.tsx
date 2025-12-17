import { Check, Zap, Building2, Rocket } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import PageTransition from '@/components/PageTransition';
import FadeIn from '@/components/FadeIn';

const Pricing = () => {
  const plans = [
    {
      name: 'Starter',
      icon: Zap,
      price: '$99',
      period: '/month',
      description: 'Perfect for small businesses getting started with AI automation.',
      features: [
        '1 AI Agent',
        'Up to 1,000 conversations/month',
        'Email support',
        'Basic analytics',
        'WhatsApp integration',
        'Standard response time',
      ],
      cta: 'Get Started',
      popular: false,
    },
    {
      name: 'Professional',
      icon: Building2,
      price: '$299',
      period: '/month',
      description: 'For growing businesses that need more power and flexibility.',
      features: [
        '5 AI Agents',
        'Up to 10,000 conversations/month',
        'Priority support',
        'Advanced analytics & reports',
        'All channel integrations',
        'Custom training data',
        'Meeting scheduling',
        'Lead qualification',
      ],
      cta: 'Start Free Trial',
      popular: true,
    },
    {
      name: 'Enterprise',
      icon: Rocket,
      price: 'Custom',
      period: '',
      description: 'For large organizations with complex requirements.',
      features: [
        'Unlimited AI Agents',
        'Unlimited conversations',
        'Dedicated account manager',
        'Custom integrations',
        'SLA guarantee',
        'On-premise deployment option',
        'Advanced security features',
        'White-label options',
      ],
      cta: 'Contact Sales',
      popular: false,
    },
  ];

  const faqs = [
    {
      question: 'Can I switch plans anytime?',
      answer: 'Yes, you can upgrade or downgrade your plan at any time. Changes take effect immediately.',
    },
    {
      question: 'What happens if I exceed my conversation limit?',
      answer: 'We\'ll notify you when you\'re approaching your limit. Additional conversations are billed at a per-conversation rate.',
    },
    {
      question: 'Is there a free trial?',
      answer: 'Yes! Our Professional plan comes with a 14-day free trial. No credit card required.',
    },
    {
      question: 'What integrations are included?',
      answer: 'All plans include WhatsApp. Professional and Enterprise include Slack, Teams, CRM integrations, and more.',
    },
  ];

  return (
    <PageTransition>
      <div className="min-h-screen bg-background">
        <Navbar />
        
        <main className="pt-24 md:pt-32">
          {/* Hero Section */}
          <section className="py-16 md:py-24 relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-hero" />
            <div className="absolute top-1/3 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-3xl animate-pulse-glow" />
            
            <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
              <FadeIn>
                <div className="max-w-3xl mx-auto text-center space-y-6">
                  <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary">
                    Pricing
                  </span>
                  <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold font-display">
                    Simple, <span className="text-gradient">Transparent</span> Pricing
                  </h1>
                  <p className="text-lg text-muted-foreground">
                    Choose the plan that fits your business. All plans include our core AI technology and regular updates.
                  </p>
                </div>
              </FadeIn>
            </div>
          </section>

          {/* Pricing Cards */}
          <section className="py-16 md:py-24 relative">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <div className="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
                {plans.map((plan, index) => (
                  <FadeIn key={index} delay={index * 0.15}>
                    <div className={`relative h-full ${plan.popular ? 'md:-mt-4 md:mb-4' : ''}`}>
                      {plan.popular && (
                        <div className="absolute -top-4 left-1/2 -translate-x-1/2 z-10">
                          <span className="bg-gradient-primary text-primary-foreground px-4 py-1 rounded-full text-sm font-medium">
                            Most Popular
                          </span>
                        </div>
                      )}
                      
                      <div className={`relative h-full ${plan.popular ? 'glass-strong' : 'glass'} rounded-2xl p-8 transition-transform duration-300 hover:-translate-y-2`}>
                        {plan.popular && (
                          <div className="absolute -inset-1 bg-gradient-primary rounded-2xl opacity-20 blur-xl" />
                        )}
                        
                        <div className="relative space-y-6">
                          <div className="flex items-center gap-3">
                            <div className={`w-12 h-12 rounded-xl ${plan.popular ? 'bg-gradient-primary' : 'bg-secondary'} flex items-center justify-center`}>
                              <plan.icon size={24} className={plan.popular ? 'text-primary-foreground' : 'text-primary'} />
                            </div>
                            <h3 className="text-xl font-bold font-display">{plan.name}</h3>
                          </div>
                          
                          <div className="flex items-baseline gap-1">
                            <span className="text-4xl font-bold text-gradient">{plan.price}</span>
                            <span className="text-muted-foreground">{plan.period}</span>
                          </div>
                          
                          <p className="text-sm text-muted-foreground">{plan.description}</p>
                          
                          <ul className="space-y-3">
                            {plan.features.map((feature, fIndex) => (
                              <li key={fIndex} className="flex items-center gap-3">
                                <div className="w-5 h-5 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
                                  <Check size={12} className="text-primary" />
                                </div>
                                <span className="text-sm">{feature}</span>
                              </li>
                            ))}
                          </ul>
                          
                          <Button
                            variant={plan.popular ? 'primary' : 'outline'}
                            className="w-full"
                            size="lg"
                          >
                            {plan.cta}
                          </Button>
                        </div>
                      </div>
                    </div>
                  </FadeIn>
                ))}
              </div>
            </div>
          </section>

          {/* FAQ Section */}
          <section className="py-16 md:py-24 relative bg-secondary/20">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <div className="text-center mb-12">
                  <h2 className="text-3xl sm:text-4xl font-bold font-display">
                    Pricing <span className="text-gradient">FAQ</span>
                  </h2>
                </div>
              </FadeIn>
              
              <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
                {faqs.map((faq, index) => (
                  <FadeIn key={index} delay={index * 0.1}>
                    <div className="glass-strong rounded-2xl p-6 h-full">
                      <h3 className="font-bold font-display mb-2">{faq.question}</h3>
                      <p className="text-sm text-muted-foreground">{faq.answer}</p>
                    </div>
                  </FadeIn>
                ))}
              </div>
            </div>
          </section>

          {/* CTA Section */}
          <section className="py-16 md:py-24 relative">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <div className="glass-strong rounded-3xl p-8 md:p-12 text-center max-w-3xl mx-auto">
                  <h2 className="text-2xl sm:text-3xl font-bold font-display mb-4">
                    Not sure which plan is right for you?
                  </h2>
                  <p className="text-muted-foreground mb-6">
                    Book a call with our team and we'll help you find the perfect solution for your business.
                  </p>
                  <Button variant="primary" size="lg">
                    Book a Free Consultation
                  </Button>
                </div>
              </FadeIn>
            </div>
          </section>
        </main>

        <Footer />
      </div>
    </PageTransition>
  );
};

export default Pricing;
