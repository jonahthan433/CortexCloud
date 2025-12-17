import { Settings, Layers, Workflow } from 'lucide-react';

const CustomSolutionsSection = () => {
  const solutions = [
    {
      icon: Settings,
      title: 'Optimisation',
      description: 'We optimize workflows by connecting systems, automating tasks, and minimizing wasted time.',
    },
    {
      icon: Layers,
      title: 'Custom Projects',
      description: 'We analyze your workflows and implement AI solutions to streamline and optimize them.',
    },
    {
      icon: Workflow,
      title: 'Automation',
      description: 'We automate daily tasks like customer support and emails, saving you valuable hours.',
    },
  ];

  return (
    <section className="py-20 md:py-32 relative">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="text-center mb-12 md:mb-16">
          <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary mb-4">
            Custom Solutions
          </span>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold font-display">
            Create Your Custom <span className="text-gradient">AI Employee</span>
          </h2>
        </div>

        {/* Solutions Grid */}
        <div className="grid md:grid-cols-3 gap-8">
          {solutions.map((solution, index) => (
            <div
              key={index}
              className="group relative"
            >
              <div className="absolute -inset-1 bg-gradient-primary rounded-2xl opacity-0 group-hover:opacity-20 blur-xl transition-opacity duration-500" />
              <div className="relative glass-strong rounded-2xl p-8 h-full transition-transform duration-300 hover:-translate-y-2">
                <div className="w-14 h-14 rounded-xl bg-gradient-primary flex items-center justify-center mb-6">
                  <solution.icon size={28} className="text-primary-foreground" />
                </div>
                <h3 className="text-xl font-bold font-display mb-4">
                  {solution.title}
                </h3>
                <p className="text-muted-foreground">
                  {solution.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default CustomSolutionsSection;
